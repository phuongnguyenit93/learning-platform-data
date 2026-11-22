# Ma trận JDK, driver, Spring Data và giao thức sau nâng cấp

> **Chương:** Nâng cấp và tương thích  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra với kiến trúc phân tán, mô hình wide-column, partition key, thiết kế bảng theo truy vấn, tính nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối ứng dụng Java.

Một lần nâng cấp Apache Cassandra có thể thành công ở cấp node nhưng thất bại ở phía ứng dụng: node mới chạy trên JDK khác, Java Driver cũ không giải mã được kiểu dữ liệu mới, Spring Data không tương thích với Spring Boot, hoặc client kết nối được nhưng chỉ thương lượng **native protocol** đời cũ. Một bài kiểm tra `SELECT 1` thành công **không chứng minh** các tính năng vector, SAI, codec, TLS, paging, prepared statements và schema mapping đều hoạt động.

Chủ đề của bài này là lập và kiểm chứng **ma trận tương thích nhiều lớp**:

1. **Cassandra server ↔ JDK chạy node Cassandra.**
2. **Ứng dụng Java ↔ JDK chạy ứng dụng ↔ phiên bản Java Driver.**
3. **Spring Boot ↔ Spring Framework/Spring Data Cassandra ↔ Java Driver do BOM quản lý.**
4. **Java Driver ↔ native protocol thực tế được thương lượng ↔ tính năng CQL cần sử dụng.**
5. **Rolling upgrade ↔ trạng thái cluster trộn phiên bản ↔ tính ổn định của read/write và tính năng mới.**

> **Quy tắc nền tảng:** “Có thể kết nối” khác “được hỗ trợ chính thức” và khác “hỗ trợ **đầy đủ** các tính năng của release mới”. Ma trận trong bài là **mốc tham khảo có phạm vi**, không thay thế release notes/BOM chính xác của các bản đang triển khai. Trước rollout, hãy chốt phiên bản **server patch, JDK distribution/build, driver patch, Spring Boot/Data patch, native protocol và tập tính năng** trong một manifest kiểm thử.

## 1. Mục tiêu học tập

Hoàn thành bài, bạn có thể:

1. Phân biệt JDK chạy **Cassandra node** và JDK chạy **dịch vụ Java**, tránh buộc chúng có cùng major version khi không cần.
2. Đọc ma trận Cassandra 4.x/5.0, Java Driver 3.x/4.x, Spring Data Cassandra 4.5/5.0 và Spring Boot 3.5/4.0 như **những trục tương thích khác nhau**.
3. Xác định native protocol đã thương lượng bằng Java Driver, giải thích v4/v5 và ảnh hưởng của mixed-version cluster.
4. Nhận diện rủi ro thay đổi groupId/artifact, classpath, API khi nâng Java Driver hoặc Spring Data.
5. Tạo bài kiểm tra trước/sau nâng cấp cho kết nối, prepared statements, UDT/collections, TLS, paging, CL, vector/SAI và hiệu năng.
6. Viết kế hoạch rolling upgrade, canary, rollback/roll-forward và cổng phê duyệt để không bật tính năng mới quá sớm.

## 2. Năm lớp tương thích: nhìn theo đường đi của một request

~~~mermaid
flowchart LR
    A["Java service<br/>JDK ứng dụng"] --> B["Spring Boot / Spring Data Cassandra"]
    B --> C["Java Driver + Netty/codec"]
    C --> D["Native protocol v3/v4/v5<br/>TLS, auth, prepared CQL"]
    D --> E["Cassandra node<br/>JDK server"]
    E --> F["Replica, schema, SSTable, RF/CL"]
    G["BOM + dependency tree"] -. "Chốt phiên bản" .-> B
    H["Upgrade runbook"] -. "Rolling server" .-> E
~~~

| Lớp | Câu hỏi phải trả lời | Lỗi điển hình |
|---|---|---|
| **Server runtime** | Release Cassandra này chạy trên JDK nào, JVM flags/GC nào được hỗ trợ? | `UnsupportedClassVersionError`, startup fail, GC/heap regression |
| **Java Driver runtime** | Jar driver yêu cầu JDK tối thiểu nào? API 3.x hay 4.x? | `ClassNotFoundException`, `NoSuchMethodError`, thiếu class mapping |
| **Spring stack** | Spring Boot BOM kéo Spring Data Cassandra và driver bản nào? | Dependency conflict, `BeanCreationException`, repository/template mapping lỗi |
| **Wire/native protocol** | Driver và từng server thương lượng được phiên bản nào? | Protocol negotiation failure, codec/feature unsupported |
| **Hành vi dữ liệu** | CQL type, schema, consistency, paging, token metadata có thay đổi không? | Kết nối thành công nhưng đọc/ghi khác kết quả, timeout, retry sai |

### 2.1. JDK của node và ứng dụng **không phải cùng một JDK**

Một cluster Cassandra 5.0 có thể chạy **JDK 11 hoặc 17** theo ma trận chính thức, trong khi ứng dụng Spring Boot 3.5 chạy **JDK 17**. Đó không phải mâu thuẫn: chúng là **hai tiến trình JVM độc lập** giao tiếp qua native protocol. Ngược lại, nâng JDK của application không tự nâng native protocol nếu driver/protocol còn cũ.

Ví dụ:

~~~text
Cluster Cassandra 5.0.x:
  Runtime: Java 11 hoặc 17 theo release/build

Service orders-api:
  Runtime: Java 17
  Spring Boot: 3.5.x
  Spring Data Cassandra: 4.5.x (BOM quản lý)
  Java Driver: phụ thuộc phiên bản thực tế được resolve
  Native protocol: kết quả session handshake
~~~

**Sai lầm:** ghi “JDK 17” trong tài liệu rồi không nói đó là JDK của node hay của service. Một ma trận triển khai tốt phải có **hai cột JDK riêng**.

### 2.2. Ba mức phán định tương thích

| Mức | Bằng chứng tối thiểu | Ví dụ |
|---|---|---|
| **Wire-connectivity** | TCP/TLS handshake, native protocol negotiation, auth và CQL đơn giản thành công | Driver 4.17 nối được Cassandra 5.0 để đọc bảng scalar cũ |
| **API/schema compatibility** | Code Java compile, Spring repositories, schema/UDT, mapper, paging và CL test đạt | Repository cũ đọc/ghi đúng trên cluster 5.0 |
| **Feature completeness** | Các tính năng cụ thể của Cassandra mới được driver/Spring Data hỗ trợ, test tích hợp đạt | Vector type, vector search, SAI, kiểu CQL mới |

Không được biến “driver nối được server” thành “tất cả tính năng mới được hỗ trợ”. Chỉ **phê duyệt sử dụng tính năng mới** sau khi cả server, driver, Spring Data/mapping layer và phiên bản protocol đều cho phép.

## 3. Ma trận Cassandra server ↔ JDK

### 3.1. Các dòng cần cân nhắc

| Apache Cassandra | JDK chạy node — phạm vi tham khảo | Ghi chú nâng cấp |
|---|---|---|
| **3.11.x** | Java 8 là baseline lịch sử | Nếu đang ở 3.11, xác minh yêu cầu phiên bản đích và lộ trình nâng server trước khi thay runtime |
| **4.0.x** | Java 8 và Java 11; Java 11 được hỗ trợ đầy đủ từ **4.0.2** | JVM options thay đổi giữa 8/11; tránh mang nguyên JVM flags cũ |
| **4.1.x** | Nhánh 4.x dùng ma trận 8/11 theo tài liệu và release cụ thể | Xác nhận build/bản phân phối, bản vá và chính sách support của môi trường thực |
| **5.0.x** | **Java 11 hoặc Java 17** cho binary release chính thức xây với JDK 11 | Java 8 không còn được hỗ trợ; build bằng JDK 17 không chạy trên JVM 11 |
| **Bản thử nghiệm/major mới hơn** | **Không suy từ bảng này** | Kiểm tra release notes riêng; không đưa alpha/beta vào production như GA |

Nguồn cho các mốc trọng yếu: [Cassandra Java 11 support (4.x)](https://cassandra.apache.org/doc/4.1/cassandra/getting_started/java11.html), [Cassandra 5.0 Java 17 support matrix](https://cassandra.apache.org/doc/stable/cassandra/reference/java17.html) và [Cassandra 5.0 new features](https://cassandra.apache.org/doc/stable/cassandra/new/).

**Phân biệt build và run:** tài liệu Cassandra 5.0 phân biệt source build bằng Java 11 (binary release chính thức) với thử build bằng Java 17. Bytecode build Java 17 cần runtime phù hợp; không thể lấy jar build bằng 17 chạy trên JVM 11. Chỉ nhìn `java -version` trên laptop build không đủ; ghi **JDK build và JDK runtime của node** khi build từ source.

### 3.2. Chuẩn bị JDK trước khi thay Cassandra binary

Trong môi trường node đã được phép thao tác:

~~~bash
java -version
echo "$JAVA_HOME"
nodetool version
nodetool status
~~~

Với JVM mới, rà soát:

- Các file cấu hình JVM theo release, ví dụ `jvm.options` và file options theo JDK; loại bỏ flag bị xóa/thay nghĩa.
- Heap, GC, pause time, direct/off-heap memory, container memory limits và OOM behavior.
- Cài JDK đúng package/update/security patch, không coi version string “17” đã đủ để đảm bảo hiệu năng.
- Native libraries, TLS cipher/JCA providers, PKCS#12/truststore, Netty/JNR và công cụ giám sát JVM.

Nếu node khởi động được nhưng p99 tăng do GC hoặc TLS handshake, lỗi **không phải native protocol**; cần tách riêng trục JDK/GC khỏi trục client compatibility khi so sánh.

## 4. Ma trận Java Driver ↔ Cassandra server và native protocol

### 4.1. Java Driver 3.x, 4.x và mốc 4.19

| Driver family | Runtime & API chính | Nhận định khi kết nối Cassandra 4.x/5.0 |
|---|---|---|
| **DataStax/Apache Java Driver 3.x** | API kiểu `com.datastax.driver.core.Session`; nhóm legacy | Có thể phục vụ workload CQL cũ theo bản cụ thể, nhưng không giả định hỗ trợ đầy đủ tính năng Cassandra 5.0 |
| **Java Driver 4.0–4.10** | API mới `com.datastax.oss.driver.api.core.CqlSession`, Java 8+ | Tương thích hạn chế với tính năng mới của Cassandra 4.0 do hỗ trợ protocol v5 chưa đầy đủ ở các bản đầu |
| **Java Driver 4.11+** | Native protocol v5 production-ready | Mốc quan trọng khi nâng từ Cassandra 3.x lên 4.x |
| **Java Driver 4.16–4.18** | Một số tính năng Cassandra 5.0 được hỗ trợ | Không giả định hỗ trợ mọi biến thể vector/type mới |
| **Apache Java Driver 4.19.x** | Nhánh 4.x do Apache duy trì; kiểm tra đúng module/groupId | Mốc được tài liệu tương thích đề xuất cho **đầy đủ tính năng Cassandra 5.0** của driver, vẫn cần kiểm chứng Spring layer |
| **Java Driver 5.x tương lai** | Yêu cầu/điều kiện phụ thuộc release thực tế | Một công bố kế hoạch năm 2026 nói tới Java 17+ cho 5.0; **không dùng kế hoạch làm bằng chứng một artifact đã GA** |

Mốc 4.11 cho protocol v5 được nêu trong [Java Driver upgrade guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/). Phân loại hỗ trợ tính năng Cassandra 5.0 theo patch cần đối chiếu release notes của [Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/) và danh sách tính năng ứng dụng thực sự dùng.

**Java 8+ của Driver 4.x** là yêu cầu tối thiểu của library, **không** phải lý do để chạy Spring Boot 3.5 trên Java 8: Spring Boot 3.x có yêu cầu Java runtime riêng. Quyết định cuối cùng là **giao của toàn bộ các ràng buộc**.

### 4.2. Hai tên Maven groupId dễ bị nhầm

Những thế hệ artifact phổ biến:

~~~xml
<!-- Java Driver 4.x ở giai đoạn DataStax, ví dụ 4.17.x: -->
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

~~~xml
<!-- Apache Java Driver 4.18+; chỉ dùng trực tiếp nếu không bị BOM khác quản lý: -->
<dependency>
  <groupId>org.apache.cassandra</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.19.0</version>
</dependency>
~~~

**Đừng thêm cả hai artifact vào classpath** để “đảm bảo tương thích”. Tên module Java gần giống nhưng coordinates khác có thể tạo **hai bản driver** và dependency tree khó đoán. Nếu dùng Spring Boot starter, để BOM quản lý hoặc override **có chủ đích với thử nghiệm đầy đủ**, tránh ép version qua một dependency bổ sung gây trùng.

Mốc chuyển groupId từ 4.18 trở lên và module `java-driver-core` được ghi nhận trong [Apache Java Driver repository](https://github.com/apache/cassandra-java-driver) và [upgrade guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/).

### 4.3. Driver 3 → 4 là thay API, không chỉ đổi dependency

| Java Driver 3.x | Java Driver 4.x |
|---|---|
| `com.datastax.driver.core.Cluster` và `Session` | `com.datastax.oss.driver.api.core.CqlSession` |
| Config Builder/Pooling API cũ | HOCON config, execution profiles, async/reactive API mới |
| Metadata/Token/Codec API 3.x | Driver context, metadata, codec registry và mapper 4.x |
| Prepared/bound classes 3.x | `com.datastax.oss.driver.api.core.cql.PreparedStatement` / `BoundStatement` |
| Driver metrics/routing cấu trúc cũ | Cấu hình metrics và load-balancing khác, cần so migration guide |

Một project từng dùng driver 3.x trực tiếp phải sửa import, Session lifecycle, auth/TLS, local datacenter, paging, retry policies và mapper. **Biên dịch thành công chưa đủ**: cần chạy thật với Cassandra cùng driver mới.

## 5. Native protocol: phiên bản trên dây, không phải phiên bản CQL hay SSTable

### 5.1. Phân biệt ba version number

Một request có thể liên quan:

- **Server version** — ví dụ Cassandra `5.0.x`.
- **Native protocol version** — ví dụ `V4` hoặc `V5` (định dạng message trên kết nối).
- **CQL language version** — thông tin của CQL dialect/version do server triển khai.

Ba chuỗi này **không đánh số cùng nhau**. Cassandra 5.0 không có nghĩa mỗi client phải dùng native protocol “v5.0”, và “CQL 3” không có nghĩa native protocol v3.

### 5.2. Bảng thương lượng mẫu với Java Driver 4.x

Theo tài liệu [Apache Java Driver 4.19 — Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/), driver 4 hỗ trợ native protocol **V3–V5**:

| Server version | Protocol thông dụng với Driver 4.x phù hợp | Lưu ý |
|---|---|---|
| Cassandra 2.1.x | V3 | Chủ yếu cho legacy, không là khuyến nghị môi trường mới |
| Cassandra 2.2.x/3.x | V4 | CQL scalar/collections và chức năng sẵn có trong thế hệ đó |
| Cassandra 4.x | V5 với driver hỗ trợ đầy đủ (mốc 4.11+) | Kiểm tra phiên bản driver; bản 4.x đầu có caveat V5 |
| Cassandra 5.0.x | V5 là protocol thuộc dải hỗ trợ Driver 4.x | **Tính năng Cassandra 5.0 không tự có chỉ vì V5**; cần driver patch/type codecs phù hợp |

Lúc cluster trộn Cassandra 3.x và 4.x trong quá trình rolling upgrade, driver 4 có cơ chế negotiation tương thích hỗ trợ mixed cluster, nhưng **không thể giả định mỗi kết nối đều dùng V5**. Kiểm tra protocol thực tế của session; không bật tính năng yêu cầu toàn cluster mới trước khi tất cả node đủ điều kiện.

### 5.3. Đọc protocol sau khi kết nối từ Java

Ví dụ dùng Java Driver 4.x:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

// session đã được tạo bằng config contact-points, local DC, TLS và auth.
void logCompatibility(CqlSession session) {
    System.out.println("Negotiated protocol = "
            + session.getContext().getProtocolVersion());

    Row local = session.execute(
            "SELECT release_version, cql_version FROM system.local").one();
    if (local != null) {
        System.out.println("Coordinator/local node release = "
                + local.getString("release_version"));
        System.out.println("CQL version = "
                + local.getString("cql_version"));
    }
}
~~~

**Phân biệt cách đo:** `session.getContext().getProtocolVersion()` là protocol mà driver session chọn/ghi nhận theo API hiện hành; `system.local` trả thông tin node thực hiện câu truy vấn, **không phải danh sách phiên bản của mọi replica**. Trong mixed-version cluster phải kết hợp `nodetool status`, inventory node và metadata/metrics từ nhiều endpoint.

### 5.4. Có nên ép advanced.protocol.version?

Mặc định, **để driver thương lượng tự động**. Một số driver 4.x có tùy chọn ép:

~~~hocon
# CHỈ THỬ trong lab khi tài liệu driver và phiên bản server xác nhận.
datastax-java-driver {
  advanced.protocol {
    version = V4
  }
}
~~~

Ép V4 có thể giúp xác định một lỗi negotiation khi kiểm thử, nhưng làm mất khả năng dùng các tính năng thuộc protocol mới và có thể che tình trạng mixed-version chưa được xử lý. Không đặt `V5` trên cụm Cassandra 3.x rồi kỳ vọng driver tự sửa lỗi: hãy để **auto** và ghi kết quả, chỉ force khi có lý do kỹ thuật cụ thể.

### 5.5. TLS không đồng nhất với native protocol

TLS bắt đầu bằng handshake mạng (CA/cert/SAN, cipher); native protocol được thương lượng **trong** kết nối transport phù hợp. Khi TLS handshake lỗi, driver có thể chưa gửi được native protocol startup message. Nếu native protocol version không được hỗ trợ, sửa TLS keystore không giải quyết lỗi đó. Vì vậy test phải chia hai lớp:

~~~text
TCP endpoint reachable?
  -> TLS handshake và hostname verification (nếu bật)?
     -> CQL authentication (nếu bật)?
        -> Native protocol startup/negotiation?
           -> Prepared CQL / serialization / paging?
~~~

Trật tự chi tiết các frame auth/startup phụ thuộc protocol/driver, nhưng thông điệp chính là **phân biệt tầng hỏng bằng log/exception**, không gộp tất cả thành “Cassandra không kết nối”.

## 6. Spring Data Cassandra và Spring Boot: BOM là nguồn sự thật

### 6.1. Spring Boot không đi theo số phiên bản Cassandra

| Spring Boot | Spring Data release train | Spring Data Cassandra | JDK chạy ứng dụng (định hướng) |
|---|---|---|---|
| **3.5.x** | **2025.0.x** | **4.5.x** | Java **17+** theo yêu cầu Spring Boot 3.x |
| **4.0.x** | **2025.1.x** | **5.0.x** | Java **17+** và Spring Framework 7.x theo thế hệ Boot 4 |
| **Các nhánh mới hơn** | Xem BOM của **đúng bản Boot** | Không tự suy từ nhánh server | Kiểm tra release notes/BOM và JDK tối thiểu |

Ví dụ mapping được công bố trong [Spring Data 2025.0 GA](https://spring.io/blog/2025/05/16/spring-data-2025-0-goes-ga/) và [Spring Data 2025.1.1](https://spring.io/blog/2025/12/12/spring-data-2025-1-1-2025-0-7-and-2024-1-13-released/). Các bản vá theo thời gian sẽ đổi; bảng này là **quan hệ thế hệ**, không phải toàn bộ danh sách bản được hỗ trợ đến vô hạn.

**Bẫy thường gặp:** nghe “Cassandra 5.0” rồi tự sửa `spring-data-cassandra` từ 4.5 lên 5.0 trong một dự án **Spring Boot 3.5**. Spring Data 5.0 thuộc Spring thế hệ mới; override đơn lẻ có thể gây xung đột Spring Framework/Spring Data Commons và cả dependency của driver.

### 6.2. Mẫu Maven với Spring Boot BOM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>cassandra-compat-lab</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**Mục đích:** để Boot quản lý Spring Data và các phụ thuộc liên quan, tránh gắn thêm `java-driver-core` với groupId/version khác khi chưa kiểm tra cây dependency. Đây là cấu hình **mẫu học tập**, không phải khuyến nghị giữ cố định bản Boot 3.5.0 vốn cần cập nhật patch/security. Khi thử thật, dùng bản vá đã được nhóm phê duyệt.

### 6.3. Xem dependency tree, không phán đoán từ pom.xml

~~~bash
# Lệnh Maven trong project ứng dụng, không phải node Cassandra.
./mvnw -q help:effective-pom
./mvnw dependency:tree

# Khi cần tìm bản Cassandra driver bị kéo qua nhiều dependency:
./mvnw dependency:tree -Dincludes=org.apache.cassandra:*,com.datastax.oss:*
~~~

Lệnh lọc chỉ là gợi ý; Maven plugin có thể xử lý wildcard/quotes khác nhau giữa shell, nên nếu lọc không hiển thị được gì, **đọc dependency tree đầy đủ**. Kiểm tra cả driver core, query-builder/mapper, Netty, Jackson, Guava/shaded dependencies và Spring Data Commons.

**BOM không tự bảo đảm tương thích tính năng Cassandra 5.0.** Nó bảo đảm một tập dependency nhất quán theo Spring release train. Nếu ứng dụng muốn vector/Cassandra 5 features, kiểm tra Spring Data hỗ trợ mapping và driver được quản lý có codec/tính năng phù hợp, rồi làm integration test. Chỉ override driver khi tài liệu Spring/Boot cho phép và có full regression testing.

### 6.4. Những thay đổi ở Spring Data cần kiểm chứng

- **Repository/query methods**: derived queries, `@Query`, cách bind parameter, paging/limit, count.
- **CassandraTemplate/ReactiveCassandraTemplate**: APIs, thread model, reactive backpressure và exception translation.
- **Mapping**: `@Table`, `@PrimaryKey`, `@PrimaryKeyColumn`, UDT/collections, `@Version` và converter tùy biến.
- **Session configuration**: Boot properties, auto-configuration, local datacenter, contact points, TLS/auth, retry policies.
- **Schema action**: các cấu hình tạo/xác minh schema; tránh tự động `CREATE/DROP` trên production khi thay Spring major.
- **Observation/tracing**: Micrometer/metrics ID và OpenTelemetry/logging; thay đổi observability có thể khiến báo động mất dữ liệu hoặc không có metric.

Nếu Spring Data nâng major, **đọc migration guide riêng của Spring Data Cassandra**. Không chỉ sửa dependency rồi biên dịch mà không chạy repository integration tests.

## 7. Ma trận hợp nhất: minh họa các phương án thực tế

**Các ô “cần kiểm thử” không đồng nghĩa được hỗ trợ tuyệt đối**. Bảng giúp chọn kịch bản lab, không là chứng nhận cho mọi patch/feature.

| Kịch bản | Cassandra server / JDK node | Java service / runtime | Driver / Spring stack | Native protocol mong đợi | Kết luận sơ bộ |
|---|---|---|---|---|---|
| **A — giữ legacy** | 3.11 / JDK 8 | App JDK 8 | Driver 3.x, Spring thế hệ cũ | Thường V4 | Phù hợp migration baseline, nhưng không là đích lâu dài |
| **B — lên Cassandra 4.0** | 4.0.2+ / JDK 11 | App JDK 17 | Driver 4.11+, Boot 3.5/Data 4.5 khi được hỗ trợ | V5 khi toàn cluster/driver phù hợp | Có thể kiểm thử đầy đủ app cũ, chú ý mapping/API |
| **C — Cassandra 5.0 với ứng dụng 3.5** | 5.0 / JDK 11 hoặc 17 | App JDK 17 | Driver 4.19.x được chọn qua dependency plan, Boot 3.5/Data 4.5 | V5 | **Tính năng cơ bản:** test; tính năng vector/SAI: test từng lớp và BOM override |
| **D — nâng cả Spring stack** | 5.0 / JDK 17 | App JDK 17+ | Boot 4.0/Data 5.0 và driver BOM phù hợp | V5 | Được lợi từ Spring generation mới nhưng tăng phạm vi thay đổi |
| **E — ép giao thức cũ** | 5.0 / JDK 11/17 | App JDK 17 | Driver 4.x ép V4 | V4 | Chỉ dùng cho điều tra khi được hỗ trợ, không là mặc định production |

**Điều không được kết luận từ bảng:** chạy Boot 4.0/Driver mới trên Cassandra 5.0 **không tự bảo đảm** cluster đã bật SAI, index schema đúng, feature flags được hỗ trợ hoặc sẵn sàng nâng SSTable format.

### 7.1. Một hàng manifest tương thích đủ để audit

~~~yaml
service: orders-api
environment: staging
server:
  cassandra_release: "5.0.x (điền patch thực)"
  node_jdk: "17.0.x (điền vendor/build)"
  topology: "dc1, RF=3 (ví dụ; đo thực)"
application:
  runtime_jdk: "17.0.x (điền vendor/build)"
  spring_boot: "3.5.x (BOM thực)"
  spring_data_cassandra: "4.5.x (resolved)"
  java_driver: "org.apache.cassandra:java-driver-core:4.19.x (nếu thực sự dùng)"
wire:
  negotiated_protocol: "V5 (đọc từ session, không đoán)"
  tls: "CA/SAN đúng; native port được phép"
features_under_test:
  - prepared_statements
  - pagination
  - ttl_and_writetime
  - udt_or_collection_mapping
  - LOCAL_QUORUM
  - vector_or_sai_if_used
approval:
  evidence: "test artifacts + SLO"
  rollback_owner: "runbook owner"
~~~

Manifest này chỉ là **template**, không phải kết quả đo. Chỉ ghi `V5` vào manifest **sau** khi thu thập thực tế; ví dụ dùng key string không nhạy cảm, không đưa password/TLS private key vào YAML.

## 8. Ma trận kiểm thử trước và sau nâng cấp

### 8.1. Phải kiểm thử tính đúng trước hiệu năng

| Nhóm | Kiểm thử tích hợp tối thiểu | Lỗi dễ bị bỏ qua |
|---|---|---|
| Kết nối | TLS CA/SAN, CQL auth, local DC, CL, reconnect | Một số node cert sai hoặc driver chọn remote DC |
| CQL scalar | `int`, `bigint`, `uuid`, `timestamp`, `decimal`, `blob` | Serialization/timezone/số lớn đổi |
| Collections/UDT | `list/set/map`, UDT frozen/non-frozen phù hợp schema | Codec/mapper không tương thích |
| Prepared statements | Prepare, execute, schema change, reconnect và reprepare | Prepare cache lỗi sau rolling upgrade |
| Paging | Nhiều page với page size nhỏ và số hàng lớn | Chỉ đọc trang đầu; paging state dùng sai query |
| Consistency | `LOCAL_QUORUM`/`LOCAL_ONE` trong RF/DC đúng, node tạm Down | Cấu hình CL/local-DC sai làm timeout |
| TTL/tombstone | `TTL()`, `WRITETIME()`, DELETE, expire, repair policy | Dữ liệu đã hết hạn hồi sinh do test thiếu |
| LWT/conditional writes | `IF NOT EXISTS`, `IF column = ...` khi có dùng | CAS semantics, exception/retry thay đổi |
| Schema migration | ALTER/UDT/index, schema agreement qua mixed nodes | Node cũ không hiểu schema mới |
| Cassandra 5 features | Vector types/functions, SAI, advanced codecs theo workload | Driver kết nối được nhưng không bind/deserialize feature |
| Hiệu năng | p50/p95/p99, throughput, error/retry rate, GC/CPU | p50 đẹp nhưng p99 và timeouts tăng |

**Đừng bật tính năng Cassandra 5 trong giai đoạn hỗn hợp phiên bản** nếu node cũ có khả năng tham gia đọc/ghi nhưng không hiểu schema/type/query mới. Cần đợi tất cả nodes đã về phiên bản đích, metadata ổn định và driver/spring tests qua đầy đủ.

### 8.2. Hai nhóm test server/app tách biệt

**Server upgrade tests**

~~~text
[ ] Mọi node Up/Normal, RF và DC/rack đúng
[ ] Không có major GC/OOM, backlog compaction/streaming bất thường
[ ] Schema agreement, read/write qua CL đã khai báo
[ ] SSTable/tombstone/repair không gây lỗi dữ liệu
[ ] Chưa vội đổi SSTable format hoặc bật feature mới
~~~

**Application upgrade tests**

~~~text
[ ] JDK app và dependency tree đúng theo BOM
[ ] Protocol thực tế và driver version được thu thập
[ ] Prepared CQL, paging, UDT/collections và TTL chạy đúng
[ ] TLS/auth/authorization/connection pool/retries hoạt động
[ ] Spring repositories/templates + mapping không thay đổi kết quả
[ ] p99 end-to-end và timeout <= SLO được phê duyệt
~~~

Nếu chỉ nâng Cassandra server, tốt nhất có **canary ứng dụng giữ nguyên driver hiện tại** và canary với driver mới để tách biến. Nếu nâng JDK app, Spring Boot, driver **đồng thời** mà test lỗi, việc truy nguyên sẽ khó hơn nhiều.

## 9. Lab Java Driver: đo protocol, CL, prepared và paging

### 9.1. Môi trường lab

Ví dụ dùng Cassandra 4.1 hoặc 5.0 trong **cluster lab** với tên DC thực tế là `dc1`, RF=3 khi có đủ ba node; nếu không, chỉnh RF/CL cho topology thật. Kiểm tra:

~~~bash
java -version
nodetool status
nodetool version
nodetool describecluster
~~~

Trong `cqlsh`:

~~~sql
SELECT release_version, cql_version FROM system.local;

CREATE KEYSPACE IF NOT EXISTS compat_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS compat_lab.events_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO compat_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  d654b0fe-7357-497f-8db4-59b165d58a0f,
  '2026-11-21',
  '2026-11-21T08:15:00Z',
  80aaeac3-1f11-4f66-877f-d9ccfca2216d,
  'compat-sample'
);
~~~

**Không test performance bằng một hàng:** lab này kiểm tra cú pháp/feature path. Muốn đánh giá latency cần nhiều token ranges, partition sizes, read/write mix, load và dữ liệu có phân phối đại diện. `IF NOT EXISTS` không cập nhật schema cũ; dùng `DESCRIBE TABLE` để so với DDL mong muốn.

### 9.2. Java Driver 4.x: session probe

Đoạn này giả định đã tạo `CqlSession session` từ cấu hình bảo mật của application, với local DC đúng. Mục đích là **kiểm tra protocol + prepared/paging**, không hard-code mật khẩu:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

void verifyCompatibility(CqlSession session) {
    System.out.println("Protocol = " +
            session.getContext().getProtocolVersion());

    Row info = session.execute(
            "SELECT release_version FROM system.local").one();
    if (info != null) {
        System.out.println("Contacted server release = " +
                info.getString("release_version"));
    }

    PreparedStatement ps = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM compat_lab.events_by_device_day " +
        "WHERE device_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement stmt = ps.bind(
            UUID.fromString("d654b0fe-7357-497f-8db4-59b165d58a0f"),
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T00:00:00Z"),
            Instant.parse("2026-11-22T00:00:00Z"),
            100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(20);

    long startedNs = System.nanoTime();
    ResultSet rs = session.execute(stmt);
    int rows = 0;
    for (Row row : rs) {
        UUID eventId = row.getUuid("event_id");
        Instant eventTime = row.getInstant("event_time");
        if (eventId == null || eventTime == null) {
            throw new IllegalStateException("Unexpected null key fields");
        }
        rows++;
    }
    double elapsedMs = (System.nanoTime() - startedNs) / 1_000_000.0;
    System.out.println("Rows=" + rows + ", full-consumption-ms=" + elapsedMs);
}
~~~

Ở đây:

- `LOCAL_QUORUM` cần RF/DC hợp lệ; nếu lab một node nhưng đặt RF=3, kết quả không có ý nghĩa/không sẵn sàng.
- `setPageSize(20)` chỉ là cỡ trang mong muốn, không đảm bảo luôn đúng 20 hàng mỗi page.
- Vòng lặp duyệt **tất cả trang** nếu có; latency khác đo chỉ trang đầu.
- Việc `SELECT system.local` trả một node release không bảo đảm cluster đồng nhất.
- Đo cho **driver/Spring BOM khác nhau** theo cùng data/CL để phát hiện thay đổi API và hành vi.

### 9.3. Test protocol v4 so với v5

Tạo hai cấu hình lab giống nhau, chỉ khác:

~~~hocon
# A: mặc định — KHÔNG đặt advanced.protocol.version.
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = "dc1"
}
~~~

~~~hocon
# B: ép thấp hơn, CHỈ khi tài liệu driver/server cho phép.
datastax-java-driver {
  basic.load-balancing-policy.local-datacenter = "dc1"
  advanced.protocol.version = V4
}
~~~

Chạy cùng bộ truy vấn đơn giản để kiểm tra phương án B có thể hoạt động **với tính năng cần dùng**. Nếu feature mới yêu cầu V5 hoặc codec mới, case B có thể bị từ chối; đó là kết quả quan trọng của ma trận, không phải lỗi cần “tắt feature” trong production.

Đừng dùng ép protocol để che việc Cassandra cluster chưa hoàn tất nâng cấp hoặc một driver quá cũ. Sau kiểm thử, đưa production về **negotiation tự động** khi không có lý do được phê duyệt.

## 10. Rolling upgrade: thứ tự thay đổi và cổng phê duyệt

### 10.1. Đặc điểm của nâng cấp từng node

Cassandra là hệ phân tán nhiều replica. Trong một thời gian ngắn có thể có cả node cũ và mới. Mục tiêu của rolling upgrade là giữ RF/CL đáp ứng yêu cầu khi lần lượt rút node để nâng cấp, nhưng **không có lời hứa mọi cặp major version được trộn tùy ý**.

Hãy dùng **đường nâng cấp được tài liệu release hỗ trợ**, không nhảy bỏ qua major/minor chỉ vì gói cài đặt có thể khởi động. Với các nâng cấp như 3.x → 4.x → 5.x, phải đọc release-specific upgrade notes và những bước trung gian bắt buộc; không thực hiện nhiều major upgrades cùng lúc khi chưa có hướng dẫn chính thức.

### 10.2. Trình tự có thể kiểm chứng

~~~mermaid
flowchart TD
    A["Inventory release/JDK/driver/Boot/BOM/protocol"] --> B["Chốt đường nâng cấp và backup/restore drill"]
    B --> C["Nâng driver/app canary tương thích cả hai thế hệ server"]
    C --> D["Staging mixed-version cluster + feature regression"]
    D --> E["Nâng node canary, theo dõi RF/CL/latency/repair"]
    E --> F{"Canary đạt SLO và không lỗi dữ liệu?"}
    F -->|Không| G["Stop / đánh giá rollback hoặc roll-forward"]
    F -->|Có| H["Rolling từng node/nhóm an toàn"]
    H --> I["Cluster đồng nhất, schema agreement, repair/compaction ổn"]
    I --> J["Nâng Spring/driver thêm nếu cần, test lại"]
    J --> K["Chỉ sau cùng bật tính năng CQL mới / SAI / vector"]
~~~

**Tập trung vào bất biến:** không phá schema mà node cũ không hiểu, không thay protocol config tùy tiện, không để một DC xuống dưới số replica cần thiết cho CL ứng dụng, không xóa snapshot trước khi có rollback plan.

### 10.3. Những việc cần hoãn đến sau khi toàn cluster lên đích

- Tạo kiểu dữ liệu/vector/function/index chỉ phiên bản mới hiểu.
- Chuyển SSTable sang định dạng/feature không đọc được bởi node cũ; đánh giá tương thích trước khi chạy `upgradesstables` hoặc bật lựa chọn rewrite.
- Thay đổi schema/replication/compaction strategy không cần thiết trong cùng maintenance window.
- Gỡ bỏ thư viện/driver legacy trên ứng dụng chưa được kiểm thử, khi rollback còn dựa vào chúng.
- Bật một giao thức/bật cipher không tương thích giữa client và các endpoint cũ.

**Downgrade là điểm cần thận trọng:** sau khi server mới đã ghi metadata/SSTable format hoặc schema mới, không giả định chỉ “cài lại binary cũ” là quay về được. Đôi khi **roll-forward** đến bản đã sửa hoặc restore từ backup phù hợp release là phương án an toàn hơn. Phải lập chiến lược trước khi triển khai.

### 10.4. Stop conditions rõ ràng

| Chỉ dấu | Quyết định vận hành |
|---|---|
| Node có trạng thái Down/Joining bất thường, một DC không còn đủ replica | **Dừng rollout**, điều tra topology/streaming |
| Read/write timeout tăng, latency p99 vượt SLO | Dừng, so CL/retries/client pools, CPU/disk/GC |
| Driver gặp protocol/codec/prepare errors | Dừng ứng dụng canary hoặc server step liên quan, không bật feature mới |
| Schema disagreement kéo dài | Hoãn DDL và bước nâng tiếp, xử lý agreement |
| Compaction/repair/streaming backlog tăng không kiểm soát | Điều tiết rollout, chờ headroom |
| Authentication/TLS failure xuất hiện ở một số node | Kiểm tra truststore/cert/SAN và driver routing toàn cluster |
| Bắt đầu thấy dữ liệu thiếu/sai TTL/tombstone/LWT | Dừng, điều tra tính đúng và chiến lược phục hồi |

Không chạy tiếp chỉ vì “đa số request vẫn thành công”: khi RF=3 và CL=QUORUM, một replica có thể lỗi nhưng ứng dụng vẫn trả kết quả trong khi rủi ro sẵn sàng tăng cao.

## 11. Thực hành Spring Data Cassandra: test repository sau nâng cấp

### 11.1. Mô hình repository đơn giản

Với Spring Boot/Spring Data có cấu hình Cassandra hợp lệ, ví dụ mapping:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customers_by_id")
public class CustomerRow {
    @Id
    private UUID id;
    private String displayName;

    public UUID getId() { return id; }
    public void setId(UUID id) { this.id = id; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerRepository
        extends CassandraRepository<CustomerRow, UUID> {
}
~~~

Schema CQL tương ứng trong **lab**:

~~~sql
CREATE TABLE IF NOT EXISTS compat_lab.customers_by_id (
    id uuid PRIMARY KEY,
    display_name text
);
~~~

**Lưu ý về naming strategy:** Spring Data có quy tắc chuyển thuộc tính Java sang tên cột. Nếu muốn chắc chắn `displayName ↔ display_name` theo phiên bản/convention, chỉ định `@Column("display_name")` hoặc kiểm tra mapping thật. Trong dự án production, không để schema tự sinh mù quáng khi upgrade major Spring Data.

### 11.2. Các bài test cần giữ ổn định

- `save()`/`findById()`/`deleteById()` có cùng semantics với baseline; không dùng repository ID generator gây trùng khóa.
- `@Column`/`@PrimaryKeyColumn` với composite partition/clustering key được ánh xạ đúng.
- Converters cho `Instant`, `LocalDate`, `BigDecimal`, UDT và collection không đổi ý nghĩa.
- Repository query với `ALLOW FILTERING`, LIMIT/ordering không bị coi là thành công chỉ vì biên dịch.
- Transaction annotations không biến Cassandra thành ACID cross-partition; LWT/conditional semantics vẫn phải test riêng.
- Reactive stream có backpressure và error propagation theo đúng driver/Spring generation.

Nếu nâng cùng Spring Boot 4 và Spring Data 5, cần test lại auto-configuration, dependency injection, logging/metrics, test slices, actuator health và mạch TLS/auth riêng; **đây là một đợt nâng platform Java**, không chỉ Cassandra.

## 12. Bảng thực nghiệm, kết luận và checklist

### 12.1. Ma trận kết quả cần điền bằng số liệu

| Case | Server/JDK node | App JDK/Boot/Data | Driver/groupId | Protocol đo được | Query/feature | p99/timeout | Pass/Fail |
|---|---|---|---|---|---|---|---|
| Baseline | _điền_ | _điền_ | _điền_ | _điền_ | CQL + prepared | _điền_ | _điền_ |
| Server canary mới | _điền_ | _giữ baseline_ | _giữ baseline_ | _điền_ | CL/TLS + paging | _điền_ | _điền_ |
| Driver canary mới | _giữ server_ | _điền_ | _điền_ | _điền_ | UDT/codec + prepare | _điền_ | _điền_ |
| Full server upgraded | _điền_ | _giữ app_ | _điền_ | _điền_ | Repair/stream/read-write | _điền_ | _điền_ |
| New feature canary | _điền_ | _điền_ | _điền_ | _điền_ | SAI/vector nếu dùng | _điền_ | _điền_ |

Không điền số liệu giả định. Một phép thử với `SELECT release_version` chỉ kiểm tra một node có trả lời, **không** có sức chứng minh p99, repair, schema agreement hay feature completeness.

### 12.2. Checklist phê duyệt

- [ ] Đã kiểm kê **JDK node** và **JDK ứng dụng** riêng rẽ (vendor/build/patch).
- [ ] Đã chốt đường nâng cấp Cassandra được hỗ trợ, không nhảy major tùy ý.
- [ ] Đã ghi Spring Boot và Spring Data release train/BOM cùng dependency tree **đã resolve**.
- [ ] Không có hai bản `java-driver-core` từ hai groupId vào classpath.
- [ ] Đã phân biệt Java Driver 3.x API và 4.x API nếu có migration client.
- [ ] Đã ghi native protocol thực tế bằng `session.getContext().getProtocolVersion()`.
- [ ] Đã kiểm tra prepared CQL, paging, UDT/collections, TTL, CL và TLS.
- [ ] Tính năng Cassandra mới chỉ được bật sau khi toàn cluster, driver và mapper đã hỗ trợ.
- [ ] Có canary, stop conditions, snapshot/backup, restore drill và kế hoạch roll-forward/rollback.
- [ ] Đã theo dõi per-DC/node metrics, p50/p95/p99, timeout/retry và stream/repair backlog.
- [ ] Đã hoàn thành repository/template tests và Java runtime tests trước khi chuyển lưu lượng toàn phần.
- [ ] Đã lưu manifest thực, release notes, kết quả QA và quyết định phê duyệt.

## 13. Bài tập vận dụng

### Bài 1 — Hai JDK khác nhau

Cluster Cassandra 5.0 chạy JDK 11; service Spring Boot 3.5 chạy JDK 17 và Java Driver 4.x. Có bắt buộc đổi JDK node sang 17 để service kết nối không?

**Đáp án:** không. JDK node và app độc lập; native protocol nối hai process. Cần xác minh Cassandra patch/driver patch, negotiated protocol, TLS/auth và API/feature compatibility, chứ không buộc đồng nhất JVM major.

### Bài 2 — Kết nối thành công nhưng vector fail

Một service dùng driver 4.11 kết nối Cassandra 5.0 và đọc scalar CQL thành công, nhưng không bind được một số giá trị vector. Đội triển khai nói “Cassandra 5 đã chạy nên driver chắc chắn hỗ trợ”. Đúng hay sai?

**Đáp án:** sai. Driver 4.11 có hỗ trợ protocol V5 nhưng **không đồng nghĩa đầy đủ Cassandra 5.0 features**. Cần driver patch tương thích với vector type, codec, Spring Data mapping và test tính năng trên schema thực; mốc driver 4.19 là tham khảo quan trọng.

### Bài 3 — Nâng Spring Data sai release train

Ứng dụng Boot 3.5 đang dùng Spring Data Cassandra 4.5 qua BOM. Một developer tự đặt `spring-data-cassandra:5.0.x` mà không nâng Boot. Nguy cơ gì?

**Đáp án:** Spring Data 5.0 thuộc thế hệ Spring Framework/Boot mới hơn, dẫn đến binary incompatibility, auto-configuration và classpath conflicts. Nên theo BOM của Boot hoặc chủ động nâng cả platform rồi test.

### Bài 4 — Trộn driver artifacts

Classpath xuất hiện cả `com.datastax.oss:java-driver-core:4.17.0` và `org.apache.cassandra:java-driver-core:4.19.0`. Đây có phải cách hỗ trợ mọi server không?

**Đáp án:** không. Hai artifact rất gần nhau ở mã/API có thể tạo trùng class và xung đột transitive dependencies. Giải quyết dependency tree, chỉ giữ một driver family/version được hỗ trợ.

### Bài 5 — Rolling mixed-version

Cluster đang trộn Cassandra 3.11 và 4.x theo lộ trình nâng được hỗ trợ. Developer lập tức tạo schema với tính năng chỉ Cassandra 4.x hiểu rồi cho service mới chạy. Vì sao nguy hiểm?

**Đáp án:** node cũ chưa hiểu metadata/tính năng, routing và protocol may negotiate lower. Phải giữ schema/feature set tương thích trong giai đoạn hỗn hợp; đợi mọi node ổn định rồi mới bật feature và test.

### Bài 6 — Đọc protocol đúng nguồn

Java Driver 4.x in ra `V4` trong khi một node Cassandra 4.x đã Up/Normal. Có thể kết luận driver “không hỗ trợ Cassandra 4” không?

**Đáp án:** chưa thể. Cluster có thể còn node 3.x, driver patch cũ, protocol bị ép, hoặc session chọn mức phù hợp với mixed-version/compatibility. Kiểm tra node versions, driver patch, cấu hình override, logs và thử negotiation tự động.

## 14. Tài liệu tham khảo

1. Apache Cassandra Documentation — [Support for Java (Cassandra 5.0: JDK 11/17)](https://cassandra.apache.org/doc/stable/cassandra/reference/java17.html).
2. Apache Cassandra Documentation — [Support for Java 11 (Cassandra 4.x)](https://cassandra.apache.org/doc/4.1/cassandra/getting_started/java11.html).
3. Apache Cassandra Documentation — [What's new in Cassandra 5.0](https://cassandra.apache.org/doc/stable/cassandra/new/): vector, SAI, trie SSTables, JDK 17.
4. Apache Java Driver 4.19 — [Native Protocol](https://apache.github.io/cassandra-java-driver/4.19.0/core/native_protocol/): V3–V5, negotiation và protocol override.
5. Apache Java Driver 4.19 — [Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): Driver 3 → 4, mốc V5 production-ready và API changes.
6. Apache Java Driver — [Repository and Maven coordinates](https://github.com/apache/cassandra-java-driver): groupId `org.apache.cassandra` cho driver được Apache duy trì.
7. Spring Data — [2025.0 release: Spring Data Cassandra 4.5 và Spring Boot 3.5](https://spring.io/blog/2025/05/16/spring-data-2025-0-goes-ga/).
8. Spring Data — [2025.1 release: Spring Data Cassandra 5.0](https://spring.io/blog/2025/12/12/spring-data-2025-1-1-2025-0-7-and-2024-1-13-released/).
9. Spring Data Cassandra — [Reference Documentation](https://docs.spring.io/spring-data/cassandra/reference/): repositories, mapping, configuration, migration.
10. Spring Boot — [3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) và [4.0 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.0/appendix/dependency-versions/coordinates.html): đối chiếu phiên bản thư viện được BOM resolve.
11. Apache Cassandra Documentation — [Operations and Upgrade Guidance](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/): quy trình, thay đổi phiên bản và giới hạn rollout.
