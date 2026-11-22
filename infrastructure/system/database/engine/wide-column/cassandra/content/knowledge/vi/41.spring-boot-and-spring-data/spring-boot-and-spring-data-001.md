# Cấu hình Cassandra trong Spring Boot và ma trận phiên bản thư viện

## 1. Tình huống: cùng một ứng dụng, ba môi trường và bốn lớp thư viện

Một nhóm xây ứng dụng **Java/Spring Boot** lưu sự kiện cảm biến vào **Apache Cassandra**. Trên máy phát triển, ứng dụng kết nối thành công với Cassandra một node. Lên staging, nó báo `NoHostAvailable` hoặc lỗi xác thực. Đến production, một lập trình viên nâng riêng phiên bản Java Driver trong `pom.xml`, trong khi Spring Boot vẫn quản lý Spring Data Cassandra theo bộ dependency cũ; hệ thống khởi động nhưng một số repository hoặc codec gặp lỗi runtime.

Vấn đề không nằm ở một dòng YAML duy nhất. Khi dùng Cassandra với Spring Boot, có ít nhất **bốn lớp** cần phối hợp:

1. **Spring Boot**: auto-configuration, dependency management/BOM, profiles, lifecycle, Actuator và externalized configuration.
2. **Spring Data Cassandra**: entity mapping, `CassandraTemplate`, repositories, mapping/conversions và query abstraction.
3. **Apache Cassandra Java Driver**: `CqlSession`, native protocol, routing, pooling, request timeout, TLS, authentication và paging.
4. **Cassandra server/cluster**: CQL schema, partition/clustering key, replication factor, datacenter, consistency level, compaction/repair và disk/network.

Đổi phiên bản của lớp này **không tự động** khiến lớp khác tương thích. Đồng thời, file cấu hình Spring hợp lệ **không bảo đảm** truy vấn Cassandra hiệu quả: một repository vẫn có thể phát câu CQL thiếu partition key, hoặc một query đọc quá nhiều SSTable/tombstone.

Đây là bài thuộc chương **Spring Boot và Spring Data** trong mô-đun **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, hướng tới hiểu kiến trúc phân tán, mô hình wide-column, replication/CL, thực hành CQL và kết nối từ Java.

**Mục tiêu học tập:**

1. Phân biệt trách nhiệm của Spring Boot starter, Spring Data Cassandra, Java Driver và Cassandra server.
2. Cấu hình `spring.cassandra.*` trên **Spring Boot 3.x**, tách dev/staging/prod và biết vì sao Boot 2.x có thể dùng prefix khác.
3. Dùng BOM thay vì ghép ngẫu nhiên version; đọc **ma trận tương thích theo dòng phát hành** và xác minh dependency thật bằng Maven/Gradle.
4. Tạo CQL schema, entity composite primary key, repository và service với **Spring Data Cassandra**.
5. Hiểu khác nhau giữa repository/template, truy cập `CqlSession` trực tiếp, mapper của Java Driver và reactive Cassandra.
6. Áp dụng local DC, RF/CL, request deadline, paging, TLS, role ít quyền, secrets và health checks.
7. Chẩn đoán lỗi autoconfiguration, dependency mismatch, schema drift, auth và hiệu năng; lên kế hoạch nâng cấp có test/rollback.

> **Phạm vi/version:** ví dụ cấu hình chính nhắm tới **Spring Boot 3.x** với Java 17+ và Spring Data Cassandra tương ứng. Ma trận ở mục 5 mô tả **các dòng major/minor định hướng**, không phải khóa phiên bản patch của mọi bản phát hành. Để chọn đúng artifact và version hiện hành, phải kiểm tra **Spring Boot BOM, release notes, Spring Data release train, Java Driver và Cassandra support matrix** của chính phiên bản dự định triển khai. Không xem số phiên bản minh họa là khuyến nghị “mới nhất”.

## 2. Bốn lớp kết nối và luồng một request Cassandra

~~~mermaid
flowchart TD
    A["REST Controller / Scheduled job"] --> B["Service: validation + auth + deadline"]
    B --> C["Spring Data Repository / CassandraTemplate"]
    B --> D["CqlSession Core API khi cần CQL riêng"]
    C --> E["Spring Data Cassandra mapping/conversions"]
    E --> D
    D --> F["Java Driver: pool, routing, timeout, retry, TLS"]
    F --> G["Cassandra coordinator"]
    G --> H["Natural replicas theo token + RF + CL"]
    H --> I["Memtable, SSTable, commit log, disk"]
~~~

| Lớp | Cung cấp | Không cung cấp |
| --- | --- | --- |
| **Spring Boot** | Tạo bean, cấu hình qua `application.yml`, profile, lifecycle, BOM và observability tích hợp. | Không tự tạo data model tối ưu theo truy vấn hay đảm bảo dữ liệu nằm đúng partition. |
| **Spring Data Cassandra** | `@Table`, `@PrimaryKeyClass`, `CassandraRepository`, `CassandraTemplate`, mapping/converter và repository query. | Không tự cung cấp SQL join, JPA persistence context/dirty checking hoặc transaction đa partition kiểu RDBMS. |
| **Java Driver 4.x** | `CqlSession`, native protocol, prepared statements, node discovery, token-aware routing khi có đủ key, paging và retries. | Không tự quyết định RF/CL, giải quyết hot partition hoặc sửa `ALLOW FILTERING` tốn kém. |
| **Cassandra server** | CQL storage, token placement, replica reads/writes, repair/compaction, tombstone/TTL và replication. | Không biết service đang dùng profile Spring nào hoặc HTTP deadline của gateway. |

### 2.1. Auto-configuration không phải phép màu

Khi classpath có các starter và không bị custom bean vô hiệu hóa, Spring Boot có thể cấu hình `CqlSession`, hạ tầng Spring Data và repositories. Nhưng nó cần những dữ liệu thiết yếu như **contact points, local datacenter, keyspace, auth và TLS** phù hợp. Một `CqlSession` kết nối được chỉ chứng minh đường native protocol tới một số node hoạt động; không chứng minh:

- Mọi node đang `UN`, replica đủ quorum hoặc cluster không có pending repair.
- Bảng CQL đã tồn tại và mapping `@PrimaryKey` trùng primary key thật.
- API có giới hạn số bucket/page/byte và consistency level đúng hợp đồng.
- Tài khoản chỉ có quyền cần thiết và kết nối được xác thực peer/TLS đầy đủ.

### 2.2. Đừng nhầm Spring Data Cassandra với Java Driver mapper

**Spring Data Cassandra** là abstraction của Spring, với `CassandraRepository`, `CassandraTemplate` và `@Table`. **Java Driver Object Mapper** là mô-đun riêng của Driver 4.x với `@Entity`, `@Dao`, `@Mapper` và annotation processor. Hai hệ mapping **không có annotation thay thế cho nhau**.

Một project có thể dùng Spring Data cho CRUD và `CqlSession` cho CQL chuyên biệt, nhưng không nên bật đồng thời hai bộ mapper chỉ vì thư viện có sẵn. Cần ranh giới rõ ràng và tránh cùng một nghiệp vụ tạo nhiều truy vấn không kiểm soát.

## 3. Chọn starter: blocking hay reactive?

### 3.1. Maven BOM với Spring Boot parent

Ví dụ **project Spring Boot 3.x** dùng Spring Data Cassandra blocking:

~~~xml
<!-- pom.xml: thay BOOT_VERSION bằng bản 3.x đã được dự án duyệt. -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.telemetry</groupId>
  <artifactId>telemetry-cassandra</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
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
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
~~~

**`3.4.0` ở đây là một ví dụ cố định để biểu diễn cấu trúc POM**, không phải lời khuyên dùng bản patch đầu tiên cho production. Dự án thật nên chọn **patch đã được hỗ trợ/kiểm thử**, sau đó giữ nhất quán bằng lock/dependency management và quy trình cập nhật bảo mật.

**Điểm quan trọng:** không tự thêm `<version>` cho `spring-data-cassandra`, `java-driver-core` hoặc các module Spring Data nếu đã dùng BOM Boot và chưa có lý do được kiểm chứng. BOM chọn **bộ dependency tương thích tại mức phát hành**, còn override từng artifact có thể tạo `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi codec.

### 3.2. Reactive starter là lựa chọn kiến trúc, không phải booster miễn phí

Nếu ứng dụng cần pipeline Reactive Streams từ WebFlux/Reactor tới Cassandra, các phiên bản Boot hỗ trợ starter reactive tương ứng, thường là `spring-boot-starter-data-cassandra-reactive`. Khi dùng cần:

- Xác minh **artifact/phiên bản cụ thể** trong BOM dự án.
- Dùng repository/template reactive theo hướng dẫn Spring Data, với `Mono`/`Flux` và demand semantics phù hợp.
- Không gọi `block()` trên Netty/event-loop; giới hạn concurrency/buffer và query fan-out.
- Không chuyển toàn bộ app từ Spring MVC sang reactive chỉ để mong CQL query nhanh hơn.

~~~text
Blocking application:
  Spring MVC -> CassandraRepository / CassandraTemplate

Reactive application:
  Spring WebFlux -> ReactiveCassandraRepository /
                    ReactiveCassandraTemplate

Core Driver option:
  CqlSession -> executeAsync -> CompletionStage<AsyncResultSet>
~~~

**`CompletionStage` không tự là `Flux<Row>`** và một kết quả bất đồng bộ có thể chỉ chứa trang đầu. Trường hợp lớn cần xử lý demand/paging rõ ràng.

## 4. BOM và dependency graph: nguồn sự thật của version runtime

### 4.1. BOM quản lý những gì?

Spring Boot BOM (`spring-boot-dependencies`) quản lý một tập phiên bản gồm Spring Framework, Spring Data release train, driver và các thư viện liên quan. Nếu dùng Spring Boot parent, phần dependency management thường được áp dụng tự động. Nếu dự án dùng một parent riêng, có thể **import BOM**:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-dependencies</artifactId>
      <version>${spring-boot.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

Trong trường hợp import BOM, property `spring-boot.version` phải được định nghĩa từ version đã duyệt; không copy cả parent và BOM vào POM nếu không hiểu quy tắc quản lý version. Với **Gradle**, dùng plugin/BOM/dependency-management strategy phù hợp, kiểm tra resolved configuration, không suy theo file `build.gradle` khi có platform hoặc resolution overrides.

### 4.2. Ba con số khác nhau thường bị nhầm

~~~text
Spring Boot version        : version của framework/bootstrap + BOM
Spring Data Cassandra ver. : version module dữ liệu Spring
Java Driver version        : version native protocol client thực thi
Apache Cassandra server   : version cluster database
~~~

Ví dụ **Spring Boot 3.4.x** không đồng nghĩa Cassandra server **3.4.x**, cũng không đồng nghĩa Java Driver **3.4.x**. Tên version của các dự án **không chạy song song**.

### 4.3. Kiểm tra dependency thật (không chỉ POM khai báo)

~~~bash
# Chạy trong dự án Maven của chính ứng dụng, không chạy trong lab Cassandra.
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-cassandra
./mvnw dependency:tree -Dincludes=com.datastax.oss:java-driver-core
./mvnw dependency:tree -Dincludes=org.springframework:spring-core

# Ví dụ Gradle nếu dự án thực dùng Gradle:
./gradlew dependencyInsight --dependency spring-data-cassandra --configuration runtimeClasspath
./gradlew dependencyInsight --dependency java-driver-core --configuration runtimeClasspath
~~~

Tên group/artifact của Java Driver và starter **có thể đổi theo dòng phát hành**; các lệnh trên minh họa cách kiểm tra một tọa độ Driver 4.x quen thuộc, không bảo đảm mọi bản tương lai dùng cùng tọa độ. Khi kết quả trống, xem toàn bộ `dependency:tree`/resolved graph, BOM import và hướng dẫn của bản đang chạy. Ở production, lưu **resolved dependency report + SBOM/lockfile**, không chỉ version có trong `pom.xml`.

## 5. Ma trận phiên bản: Spring Boot, Spring Data, Java và Cassandra Driver

### 5.1. Ma trận dòng phát hành để định hướng

| Dòng Spring Boot | Spring Framework (dòng) | Spring Data Cassandra (dòng thông thường) | Java tối thiểu phổ biến | Cấu hình / lưu ý chính |
| --- | --- | --- | --- | --- |
| **2.7.x** | 5.3.x | **3.4.x** thuộc Spring Data 2021.2 | Java 8+ theo hỗ trợ dòng Boot | Nhiều property Cassandra thuộc `spring.data.cassandra.*`; kế hoạch nâng sang Boot 3 cần xét Jakarta/Java 17. |
| **3.0.x** | 6.0.x | **4.0.x** thuộc Spring Data 2022.0 | **Java 17+** | Spring Boot 3, Spring Framework 6, nhiều API `javax.*` chuyển `jakarta.*`. |
| **3.1.x** | 6.0.x | **4.1.x** thuộc Spring Data 2023.0 | Java 17+ | Kiểm tra các thay đổi minor của Spring Data và driver được BOM pin. |
| **3.2.x** | 6.1.x | **4.2.x** thuộc Spring Data 2023.1 | Java 17+ | Cấu hình Cassandra theo `spring.cassandra.*` trong Boot 3. |
| **3.3.x** | 6.1.x | **4.3.x** thuộc Spring Data 2024.0 | Java 17+ | Giữ BOM đồng bộ; test mapping/metrics và paging khi cập nhật. |
| **3.4.x** | 6.2.x | **4.4.x** thuộc Spring Data 2024.1 | Java 17+ | Là dòng minh họa trong POM; không tự chọn patch nếu chưa kiểm chứng. |
| **3.5.x** | 6.2.x | **4.5.x** thuộc Spring Data 2025.0 | Java 17+ | Xác minh BOM bản patch, JDK cụ thể và ràng buộc dependency. |
| **4.0.x** | 7.0.x (định hướng dòng Boot 4) | **5.0.x** thuộc dòng Spring Data mới tương ứng | Kiểm tra yêu cầu JDK của bản Boot 4 cụ thể | Nâng major: kiểm tra tài liệu migration, starter/module, package, config property và driver thực tế; **không copy cấu hình 3.x mà không test**. |

**Cách dùng bảng:** đây là **mapping dòng phát hành để học và lập kế hoạch**, không phải file lock chính thức cho bản patch bạn đang chạy. Spring Boot BOM của **một bản patch cụ thể** mới quyết định Spring Data patch, Java Driver patch, Micrometer, Reactor và các transitive dependencies. Các mốc version và tình trạng hỗ trợ có thể thay đổi; kiểm tra release train/BOM trước khi chọn release cho hệ thống mới.

### 5.2. Java Driver và Cassandra server là **hai trục riêng**

Không gán “Spring Boot 3.4 = Java Driver 4.4” hoặc “Spring Data 4.4 = Cassandra server 4.4”. Thay vào đó:

| Tầng | Cách chọn version | Điều phải kiểm chứng |
| --- | --- | --- |
| **Spring Boot + Framework** | Chọn bản Boot được hỗ trợ rồi theo BOM. | JDK, lifecycle, auto-configuration, các điểm phá vỡ của major release. |
| **Spring Data Cassandra** | Dùng dòng do BOM Boot quản lý. | Mapping annotations, repository/query API, template, reactive module. |
| **Cassandra Java Driver 4.x** | Thông thường lấy bản driver do BOM pin; override chỉ khi có lý do và compatibility test. | Native protocol, `CqlSession`, node/DC discovery, TLS/auth, codecs, metrics. |
| **Cassandra server 3.x/4.x/5.x** | Chọn theo **support matrix** của driver/Spring Data và đường nâng cấp cluster. | Protocol/feature compatibility, SSTable format, schema, RF/CL, repair/compaction. |
| **JDK** | Theo Boot/driver bản cụ thể. | Runtime/toolchain, TLS cipher, GC, Docker image, build plugin. |

**Chú ý:** driver 4.x có thể kết nối nhiều phiên bản Cassandra qua native protocol tương thích, nhưng điều đó **không tự có nghĩa mọi tính năng mới của Cassandra 5.x được Spring Data mapping hỗ trợ đầy đủ**. Đặc biệt với vector types/SAI/features mới hoặc codec tùy chỉnh, cần test thực tế và đọc ma trận của bản driver đang dùng.

### 5.3. Ví dụ xung đột dependency

~~~text
POM Boot 3.x quản lý:
  Spring Data Cassandra 4.x
  Java Driver theo BOM 4.x patch A

Developer tự force:
  java-driver-core 4.x patch B
  java-driver-query-builder patch C
  Spring Data Cassandra 4.x patch D

Tác động có thể:
  - ClassNotFoundException / NoSuchMethodError
  - khác API codec/mapper/method signature
  - module reactive/metrics không đồng bộ
  - hành vi TLS/protocol/config khác expected
~~~

Không phải mọi override đều sai: đôi khi vá bảo mật cần nâng driver trong phạm vi tương thích. Nhưng phải **đồng bộ các module cùng họ**, đọc compatibility notes, chạy clean build/integration test và cập nhật SBOM/lockfile. Không dùng **`-DskipTests`** để che lỗi tương thích.

## 6. Thiết kế keyspace và bảng Cassandra trước khi khởi động ứng dụng

### 6.1. CQL schema lab

Giả sử một DC `dc1`, có đủ node cho RF=3 và `LOCAL_QUORUM`. Chạy CQL qua `cqlsh` với role quản trị schema trên **cluster lab**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_spring
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_spring.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Lý do chọn schema:

- **Partition key kép `(device_id,event_day)`**: giới hạn lịch sử vào bucket ngày, định tuyến token/replicas theo thiết bị và ngày.
- **Clustering key `(event_time,event_id)`**: hỗ trợ range reads theo thời gian trong ngày, phân biệt hai sự kiện cùng timestamp.
- **`event_type` và `payload`** là regular columns. Nếu cần tìm tất cả sự kiện `ALARM` trên nhiều thiết bị theo site, cần cân nhắc bảng/projection theo query, không chỉ viết repository `findByEventType` rồi `ALLOW FILTERING`.
- RF 3 là chi phí ba full replicas trong `dc1`; `LOCAL_QUORUM` cần hai phản hồi local DC. Không dùng ví dụ RF 3 trên một node rồi kỳ vọng quorum thật.

### 6.2. Ghi và đọc một dữ liệu cố định

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_spring.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_spring.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

SELECT event_time, event_id, event_type, payload
FROM telemetry_spring.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

`CONSISTENCY` là lệnh **cqlsh**, không phải CQL statement truyền nguyên văn cho repository/Java Driver. Giá trị `event_day` trong ứng dụng phải lấy từ **UTC date của `event_time`**, dùng nhất quán cả ingestion và backfill. Một timezone khác có thể làm event được ghi vào partition ngày sai.

### 6.3. Schema migration không thuộc về service user

**Không cho ứng dụng production tự tạo/drop keyspace/table theo mỗi lần restart.** Quy trình thường có:

1. DDL lưu theo version, review schema và tác động token/partition/compaction.
2. Một role hoặc pipeline migration riêng có `CREATE/ALTER` cần thiết.
3. Service role chỉ `SELECT`/`MODIFY` đúng bảng.
4. Schema agreement và integration test đã qua trước khi mở traffic.
5. Migration v1/v2 nếu đổi partition/clustering key: tạo bảng mới, dual-write/CDC, backfill, reconcile và canary cutover; **không `ALTER TABLE` để đổi primary key**.

## 7. `spring.cassandra.*`: cấu hình tối thiểu trên Boot 3.x

### 7.1. File cấu hình cơ sở

~~~yaml
# src/main/resources/application.yml (ví dụ cho Spring Boot 3.x)
spring:
  application:
    name: telemetry-api
  cassandra:
    contact-points: ${CASSANDRA_CONTACT_POINTS}
    port: ${CASSANDRA_PORT:9042}
    local-datacenter: ${CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_spring
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
    schema-action: none
~~~

**Cách hiểu:**

- `contact-points` là điểm khám phá node ban đầu, **không** phải danh sách toàn bộ replica của mỗi partition. Driver theo dõi topology và có thể mở pools theo các node được discovery.
- `local-datacenter` phải đúng **tên DC trong snitch metadata của cluster**, không phải region cloud giả định. Cấu hình sai có thể gây routing bất thường/không có node khả dụng.
- `keyspace-name` là default keyspace cho một số đường Spring Data/driver; entity/table mapping vẫn cần đúng schema.
- `username/password` chỉ phù hợp nếu cluster bật authentication kiểu tương ứng. Biến môi trường là ví dụ externalized config; production có thể chọn secret manager/workload identity.
- `schema-action: none` diễn đạt ý định **không để app tự tạo/drop schema**. Xác minh tên key và `SchemaAction` theo version Boot/Spring Data cụ thể; không dựa vào việc Boot tự sửa schema production.
- Không hardcode địa chỉ/credential production vào source, và **không tự fallback** sang contact point dev nếu biến bắt buộc thiếu.

**Khác biệt quan trọng:** trên nhiều bản **Spring Boot 2.x**, prefix Cassandra có thể nằm dưới `spring.data.cassandra.*`. Trên **Boot 3.x**, ví dụ dùng `spring.cassandra.*`. Khi nâng phiên bản, dùng tài liệu **configuration metadata của bản Boot đang chạy** và kiểm tra effective properties; một property tên cũ không được bind có thể khiến app dùng default sai mà không báo ngay.

### 7.2. File `application-dev.yml` và `application-prod.yml`

~~~yaml
# application-dev.yml — dữ liệu giả, node lab, không dùng credentials prod.
spring:
  cassandra:
    contact-points: ${DEV_CASSANDRA_HOST:127.0.0.1}
    port: ${DEV_CASSANDRA_PORT:9042}
    local-datacenter: ${DEV_CASSANDRA_DC:dc1}
    keyspace-name: telemetry_spring
~~~

~~~yaml
# application-prod.yml — bắt buộc cấp biến môi trường/secret riêng.
spring:
  cassandra:
    contact-points: ${PROD_CASSANDRA_CONTACT_POINTS}
    port: ${PROD_CASSANDRA_PORT:9042}
    local-datacenter: ${PROD_CASSANDRA_LOCAL_DC}
    keyspace-name: telemetry_spring
    username: ${PROD_CASSANDRA_USERNAME}
    password: ${PROD_CASSANDRA_PASSWORD}
~~~

Ví dụ tách file để giải thích **Spring profiles**. Thực tế nên có cách gán tên biến **nhất quán, không để file base và file profile cùng định nghĩa credential khác nguồn**. Với ứng dụng cần phân biệt fail-closed, validate `spring.profiles.active`, expected cluster/DC và property bắt buộc trước khi nhận traffic; không lấy `dev` làm default khi profile production bị thiếu.

~~~bash
# Minh họa CLI chọn môi trường, không chứa password:
java -jar telemetry-api.jar --spring.profiles.active=dev
~~~

**Cảnh báo về secrets:** biến môi trường vẫn có thể lộ qua dump/log/proc introspection của actor có quyền. Production nên dùng giải pháp quản lý secrets, IAM và rotation đã được duyệt; không commit `application-prod.yml` chứa password thật hoặc in toàn bộ effective environment khi debug.

## 8. Lúc nào cần cấu hình Java Driver riêng?

Spring Boot quản lý các thuộc tính Cassandra thông thường, nhưng những hành vi như **pooling, request timeout, page size, throttler, metrics/tracing, SSL và retry policy** có thể được điều khiển ở **Driver 4.x** hoặc customizers được version hỗ trợ.

### 8.1. Ví dụ HOCON của Java Driver

~~~hocon
# Ví dụ datastax-java-driver config dùng cho thử nghiệm có kiểm soát.
datastax-java-driver {
  basic.request {
    timeout = 2 seconds
    consistency = LOCAL_QUORUM
    page-size = 100
  }
  advanced.connection.pool {
    local.size = 1
  }
  advanced.request-throttler {
    class = ConcurrencyLimitingRequestThrottler
    max-concurrent-requests = 200
    max-queue-size = 400
  }
}
~~~

**Nguyên tắc:**

1. Các con số `2s/100/200/400` là **lab values**, không phải SLO/limits chuẩn production.
2. `page-size` giới hạn **số hàng mục tiêu mỗi page**, không phải byte/page; `LIMIT` của CQL kiểm soát số hàng logic trả về trong statement.
3. `local.size` là số kết nối theo pool/node trong cấu hình driver, **không phải** tổng in-flight API requests. Native protocol multiplex nhiều requests trên connection.
4. Driver request throttler giới hạn một scope driver/session, **không tự giới hạn** HTTP queue hoặc số pod toàn fleet; cần admission/backpressure ở ứng dụng.
5. `LOCAL_QUORUM` là hợp đồng Cassandra, không phải thuộc tính “nonblocking”; với RF 3 ở một DC cần hai full replica responses.
6. **Một option có thể đã có cấu hình tương đương trong Boot**; kiểm tra thứ tự override và effective driver config cho bản Boot/Driver đang chạy, tránh HOCON và `application.yml` đặt khác nhau.
7. Tên option, class throttler và support/version có thể thay đổi. Nếu driver không nhận HOCON, đừng tuyên bố hệ thống đã throttling chỉ vì file tồn tại.

### 8.2. Không tự tạo hai `CqlSession` mà không biết

Một anti-pattern phổ biến là để Boot auto-configure `CqlSession` rồi service lại gọi `CqlSession.builder().build()` theo request. Kết quả:

- Hai hoặc nhiều pools/control connections không cần thiết, metadata discovery và TLS/auth overhead.
- Spring Data repositories dùng session A, custom code dùng session B với DC/CL/credential khác nhau.
- Khó đóng session, khó thống nhất metrics và kiểm soát backpressure.

**Hướng đúng:** ưu tiên **inject `CqlSession` được Spring quản lý** vào service khi cần Core API. Chỉ định nghĩa custom session bean khi có yêu cầu chính đáng (nhiều cluster/identity khác nhau) và biết rõ ảnh hưởng đến Boot auto-configuration và lifecycle.

## 9. Consistency, keyspace và topology không được giấu sau property

### 9.1. Local DC và natural replicas

~~~mermaid
flowchart TD
    A["Spring Repository / CqlSession"] --> B["Driver chọn coordinator theo policy/local DC"]
    B --> C["Hash partition key (device_id,event_day) thành token"]
    C --> D["Natural replicas theo NetworkTopologyStrategy"]
    D --> E["LOCAL_QUORUM: đợi 2/3 full replicas trong dc1"]
    E --> F["Trả kết quả hoặc timeout/unavailable"]
~~~

Một request có thể thành công với `LOCAL_QUORUM` nếu đủ hai replica local phản hồi; **không chứng minh tất cả replica đã có cùng dữ liệu**, không thay thế repair. Nếu ứng dụng chạy trong `dc2`, phải kiểm tra keyspace RF từng DC, local DC property và hành vi cross-DC/failover theo hợp đồng SLA.

### 9.2. Ba loại lỗi cần phân biệt

| Tình huống | Lý do có thể | Thay timeout có giải quyết? |
| --- | --- | --- |
| `Unavailable` khi `LOCAL_QUORUM` | Không đủ replica phù hợp CL/DC/RF. | **Không.** Cần kiểm tra topology/replica. |
| Read/write timeout | Replica/coord chưa trả đủ trước deadline, disk/GC/queue/compaction/network. | Có thể thay thời gian chờ, **không sửa nguyên nhân gốc**. |
| Authentication/authorization failure | Role/credentials/TLS/truststore hoặc quyền CQL. | **Không.** Sửa identity/secret/permission. |

**Không tự hạ `LOCAL_QUORUM` xuống `LOCAL_ONE` khi có lỗi**, vì đó là thay đổi consistency contract; cần phê duyệt nghiệp vụ và đo độ lệch dữ liệu nếu chính sách cho phép.

## 10. Spring Data Cassandra: ánh xạ composite primary key

Trong Cassandra, **partition key và clustering key là định danh của hàng**, không phải thuộc tính chỉ để sắp xếp trong Java. Với bảng `events_by_device_day`, ta cần ánh xạ đủ **bốn thành phần** primary key.

### 10.1. `@PrimaryKeyClass` cho khóa ghép

~~~java
// EventKey.java — Spring Data Cassandra, không phải Java Driver @Entity.
package example.telemetry;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class EventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

    @PrimaryKeyColumn(
        name = "event_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3, type = PrimaryKeyType.CLUSTERED)
    private UUID eventId;

    public EventKey() {}

    public EventKey(String deviceId, LocalDate eventDay,
                    Instant eventTime, UUID eventId) {
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.eventTime = eventTime;
        this.eventId = eventId;
    }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EventKey)) return false;
        EventKey that = (EventKey) other;
        return Objects.equals(deviceId, that.deviceId)
            && Objects.equals(eventDay, that.eventDay)
            && Objects.equals(eventTime, that.eventTime)
            && Objects.equals(eventId, that.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime, eventId);
    }
}
~~~

### 10.2. Tại sao phải ghi rõ ordinal và type?

| Annotation | Thành phần CQL | Tác dụng |
| --- | --- | --- |
| `@PrimaryKeyColumn(... PARTITIONED, ordinal=0)` | `device_id` | Phần đầu của composite partition key. |
| `@PrimaryKeyColumn(... PARTITIONED, ordinal=1)` | `event_day` | Phần thứ hai của partition key. |
| `@PrimaryKeyColumn(... CLUSTERED, ordinal=2)` | `event_time` | Clustering column đầu, thứ tự DESC. |
| `@PrimaryKeyColumn(... CLUSTERED, ordinal=3)` | `event_id` | Clustering tie-breaker. |

Các giá trị ordinal/type phải **khớp schema thực**, không tự sửa annotation để “đổi partition key” trong Cassandra. Nếu muốn thêm `event_hour` vào partition key hoặc đảo thứ tự clustering, cần **tạo bảng mới và di chuyển dữ liệu**, không chỉ sửa class Java.

`equals/hashCode` của key class phải dựa trên **định danh ổn định**, tránh dùng object mutable làm key trong một `HashMap` rồi thay `eventTime` trong lúc đang giữ nó. Với timestamp CQL, độ chính xác thường ở mức **mili giây**, không mặc định giữ mọi nanosecond của `Instant`; cần kiểm thử round-trip nếu domain mang precision cao hơn.

### 10.3. `@Table` và `@PrimaryKey`

~~~java
// EventEntity.java
package example.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("events_by_device_day")
public class EventEntity {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;

    public EventEntity() {}

    public EventEntity(EventKey key, String eventType, String payload) {
        this.key = key;
        this.eventType = eventType;
        this.payload = payload;
    }

    public EventKey getKey() { return key; }
    public void setKey(EventKey value) { key = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

**Lưu ý:** annotation của Spring Data nằm trong `org.springframework.data.cassandra.core.mapping`, **không** dùng `com.datastax.oss.driver.api.mapper.annotations.Entity`. Default keyspace của ví dụ được cấu hình bằng `spring.cassandra.keyspace-name`. Nếu có nhiều keyspace, định nghĩa chính xác đường ánh xạ và template/session, không kỳ vọng mọi repository tự tìm đúng keyspace.

## 11. `CassandraRepository`: CRUD gọn nhưng vẫn phải thiết kế CQL

### 11.1. Repository theo primary key

~~~java
// EventRepository.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.repository.query.Param;

public interface EventRepository
        extends CassandraRepository<EventEntity, EventKey> {

    // CQL có đủ partition key và clustering range, LIMIT cố định.
    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload " +
        "FROM telemetry_spring.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT 100")
    List<EventEntity> findWindow(
        @Param("deviceId") String deviceId,
        @Param("eventDay") LocalDate eventDay,
        @Param("fromInclusive") Instant fromInclusive,
        @Param("toExclusive") Instant toExclusive);
}
~~~

**Điểm mạnh:** Spring Data tạo implementation của repository, ánh xạ entity và hỗ trợ các thao tác CRUD cơ bản. `findById(EventKey)` là lookup **full primary key**. Query `findWindow` ghi **CQL tường minh** để thấy ràng buộc partition/range. Named parameter syntax, return type và chức năng query binding phải được test với đúng Spring Data Cassandra minor version.

**Không nên viết** một phương thức `findByEventType(String type)` rồi giả định Spring Data có thể quét mọi partition hiệu quả. `event_type` là regular column; Cassandra không tự hỗ trợ mọi derived query như SQL repository. Việc dùng `ALLOW FILTERING` trên bảng lớn thường tạo scan/chi phí cao, không phải giải pháp tối ưu production.

### 11.2. `save` không phải transaction insert độc nhất

`repository.save(entity)` thường tạo một mutation **upsert** phù hợp mapping của Spring Data. Nó không có transaction persistence context/dirty checking của JPA, không tự khóa hàng và không mặc định chặn việc ghi đè theo cùng primary key. Các tình huống cần kiểm tra:

- Nếu hai producer ghi cùng primary key, Cassandra hòa giải theo **timestamp mutation** và semantics của từng cell, không theo thứ tự HTTP request.
- `null` trong entity có thể được map thành **xóa cell/tombstone** hoặc được bỏ qua tùy cấu hình; không dùng entity **chỉ đọc vài cột** rồi `save` để cập nhật một field mà không hiểu chiến lược null/unset.
- TTL thường tính từ lúc ghi, không từ `event_time`; ghi lặp lại có thể ảnh hưởng retention.
- Write timeout không chứng minh chưa có replica nào ghi; retry với UUID mới có thể tạo duplicate.

**Để cập nhật riêng `payload`**, có thể dùng CQL `UPDATE ... SET payload=? WHERE` đủ full key qua template/Driver thay vì save lại entity thiếu nhiều field.

### 11.3. Service giới hạn truy vấn trong một ngày UTC

~~~java
// EventReadService.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class EventReadService {
    private final EventRepository repository;

    public EventReadService(EventRepository repository) {
        this.repository = repository;
    }

    public List<EventEntity> readOneDay(
            String deviceId, Instant fromInclusive, Instant toExclusive) {
        if (deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("deviceId is required");
        }
        if (fromInclusive == null || toExclusive == null ||
            !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid half-open window");
        }

        LocalDate day = fromInclusive
            .atZone(ZoneOffset.UTC).toLocalDate();
        Instant nextDayStart = day.plusDays(1)
            .atStartOfDay(ZoneOffset.UTC).toInstant();

        if (toExclusive.isAfter(nextDayStart)) {
            throw new IllegalArgumentException(
                "Window crosses UTC day; split into bounded buckets");
        }
        return repository.findWindow(
            deviceId, day, fromInclusive, toExclusive);
    }
}
~~~

**Lợi ích:** service không âm thầm bỏ mất ngày kế tiếp khi gọi một query chỉ có **một `event_day`**. Khi cần khoảng nhiều ngày, service phải chia thành các bucket UTC, **giới hạn bucket count/concurrency**, merge/sort và xác định **global LIMIT**. Không tạo một `findAll()` rồi lọc ở Java để né thiết kế bảng.

**Lưu ý bảo mật:** ở endpoint thật, phải xác minh caller được quyền truy cập `deviceId` trước khi gọi repository. CQL RBAC theo keyspace/table **không tự kiểm soát tenant ID** trong partition key.

## 12. Khi nào dùng `CassandraTemplate` và `CqlSession` trực tiếp?

### 12.1. Template khi không muốn khai báo repository cho mọi truy vấn

`CassandraTemplate` (hoặc `CassandraOperations`) cung cấp thao tác hướng entity/query để viết một số nghiệp vụ ngoài repository. Ví dụ sau đọc một hàng theo full key, **không tạo session mới**:

~~~java
// EventTemplateService.java
package example.telemetry;

import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class EventTemplateService {
    private final CassandraTemplate template;

    public EventTemplateService(CassandraTemplate template) {
        this.template = template;
    }

    public EventEntity getByKey(EventKey key) {
        // API template thực tế cần được đối chiếu version Spring Data.
        return template.selectOneById(key, EventEntity.class);
    }
}
~~~

Template giảm boilerplate cho mapping entity, nhưng **vẫn sinh CQL thực thi qua Java Driver**. Khi API template hoặc parameter-binding khác giữa các version, kiểm tra Spring Data reference docs và generated CQL trong integration test; không đoán rằng mọi template method luôn là partition lookup.

### 12.2. Core Driver khi cần kiểm soát statement chi tiết

`CqlSession` thường đã có bean do Boot quản lý. Inject bean này cho những use case cần **prepared statement, routing, page size, CL, tracing hoặc đọc DTO hẹp**:

~~~java
// EventSummaryService.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class EventSummaryService {
    public record EventSummary(Instant time, UUID eventId, String type) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public EventSummaryService(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_spring.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }

    public List<EventSummary> read(
            String deviceId, LocalDate day, Instant from, Instant until) {
        BoundStatement query = select.bind(deviceId, day, from, until)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        List<EventSummary> values = new ArrayList<>();
        for (Row row : session.execute(query)) {
            values.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return values;
    }
}
~~~

**Vì sao Core có thể phù hợp cho timeline?** Nó chỉ đọc ba cột thay vì `payload`, giảm bytes truyền/deserialize; chênh lệch hiệu năng chủ yếu có thể đến từ **column projection**, không nhất thiết từ việc bỏ Spring Data mapping. Khi benchmark mapper/repository và Core, phải so **cùng câu CQL/CL/page size/rows** nếu muốn kết luận overhead của abstraction.

**Không** tạo một `CqlSession` trong từng request hoặc `session.prepare(...)` cho mọi HTTP call. Một session sống lâu có pooling/metadata; prepared statement nên được tái dùng.

### 12.3. Chọn công cụ theo truy vấn

| Nhu cầu | Công cụ đáng cân nhắc | Điều không tự giải quyết |
| --- | --- | --- |
| CRUD lookup theo full primary key | `CassandraRepository` | Không cung cấp JPA transaction/dirty checking. |
| Một số truy vấn hướng entity | `CassandraTemplate` | Không biến `WHERE` thiếu partition key thành truy vấn rẻ. |
| CQL đặc thù/DTO hẹp, page/CL riêng | `CqlSession` + prepared statements | Phải tự map `Row` và theo dõi paging/timeout. |
| Reactive pipeline | Reactive repository/template hoặc driver reactive APIs | Không tự có backpressure nếu code giữ kết quả không giới hạn. |
| Đọc báo cáo đa partition/aggregation | Data model/projection/analytics chuyên biệt | Không thể sửa bằng `findAll()` hay tăng connection pool. |

## 13. Spring Data Reactive Cassandra và giới hạn backpressure

Nếu dự án chọn starter reactive phù hợp, có thể dùng `ReactiveCassandraRepository` với `Flux`/`Mono`, nhưng cần **kiểm tra bộ version Spring Boot/Spring Data/Reactor/Driver thống nhất**.

~~~java
// ReactiveEventRepository.java — dùng trong ứng dụng reactive.
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import org.springframework.data.repository.query.Param;
import reactor.core.publisher.Flux;

public interface ReactiveEventRepository
        extends ReactiveCassandraRepository<EventEntity, EventKey> {

    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload FROM telemetry_spring.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT 100")
    Flux<EventEntity> findWindow(
        @Param("deviceId") String deviceId,
        @Param("eventDay") LocalDate eventDay,
        @Param("fromInclusive") Instant fromInclusive,
        @Param("toExclusive") Instant toExclusive);
}
~~~

**Không** dùng `Flux.collectList()` cho hàng triệu rows rồi tuyên bố pipeline đã giải quyết memory. CQL có `LIMIT 100` là giới hạn **server-side** cho statement; nếu API cần nhiều bucket, vẫn cần limit số bucket, rows/byte budget, concurrency và global ordering. `timeout` của một reactive stream không chứng minh Cassandra đã ngừng xử lý yêu cầu đã gửi.

~~~java
// Trích đoạn trong reactive service, không phải class hoàn chỉnh:
Flux<EventEntity> stream = reactiveRepo
    .findWindow(deviceId, day, from, until)
    .take(50) // Client-side cap; không thay CQL LIMIT 100
    .timeout(java.time.Duration.ofMillis(800));
~~~

**Đừng trộn blocking repositories với Netty event-loop** bằng cách gọi `repository.findWindow(...)` trong một `map` callback reactive: nó có thể block thread xử lý. Nếu phải dùng blocking library trong một hệ reactive, cần mô hình chuyển scheduler riêng có giới hạn và đo ảnh hưởng; tốt hơn là chọn đường data access phù hợp ngay từ đầu.

## 14. TLS, authentication và quyền CQL trong Spring Boot

Một cấu hình kết nối có thể đúng contact points/DC nhưng vẫn **không an toàn** nếu gửi password qua plaintext hoặc tắt kiểm tra chứng chỉ server.

### 14.1. Những thành phần cần chuẩn bị

| Thành phần | Nguồn | Điều phải chứng minh |
| --- | --- | --- |
| **Client TLS** | Cassandra native transport TLS và Spring/driver SSL config. | Bắt tay TLS thành công, server identity/CA/hostname hợp lệ theo policy. |
| **Username/password hoặc auth provider** | Secret manager/identity service. | CQL role riêng theo service/environment, không dùng superuser. |
| **RBAC** | `GRANT SELECT`, `GRANT MODIFY` phù hợp. | Endpoint readonly không thể `INSERT/ALTER`, job ghi không có quyền tạo role. |
| **Network policy** | VPC/firewall/service mesh nếu phù hợp. | Dev/staging không tới production CQL trái phép, internode/JMX không bị public. |
| **Secrets rotation** | Vault/KMS/secret store. | Thay password/certificate không gây outage kéo dài, có rollback/expiry alert. |
| **Log/metrics** | Actuator, driver logging, Micrometer. | Không lộ password, raw payload hoặc partition key nhạy cảm. |

### 14.2. Ví dụ quyền theo bảng

~~~sql
-- LAB: lệnh quản trị có điều kiện, không chạy bằng role ứng dụng.
CREATE ROLE IF NOT EXISTS telemetry_reader
WITH LOGIN = true AND PASSWORD = 'replace-with-managed-secret';

GRANT SELECT ON TABLE telemetry_spring.events_by_device_day
TO telemetry_reader;

CREATE ROLE IF NOT EXISTS telemetry_writer
WITH LOGIN = true AND PASSWORD = 'replace-with-managed-secret';

GRANT SELECT ON TABLE telemetry_spring.events_by_device_day
TO telemetry_writer;
GRANT MODIFY ON TABLE telemetry_spring.events_by_device_day
TO telemetry_writer;
~~~

Các lệnh minh họa giả định Cassandra đã bật **authentication/authorization** tương ứng. String mật khẩu chỉ là placeholder lab; không sao chép vào source/ticket. Một `GRANT` không đủ nếu cluster vẫn dùng `AllowAllAuthorizer` hoặc auth config chưa được bật; kiểm tra **effective security configuration**, đồng thời bảo vệ `system_auth`, TLS và quyền OS/JMX riêng.

### 14.3. TLS/secret configuration phải theo version

Tùy phiên bản Boot/Java Driver, việc bật SSL có thể qua property như `spring.cassandra.ssl.*`, Driver config `SslEngineFactory` hoặc một **session builder/config customizer** có hỗ trợ. Không copy một snippet TLS không đúng version rồi tắt verification để “cho chạy”. Runbook cần nêu:

1. Server `client_encryption_options`/cert chain tương ứng.
2. Client trust material, hostname/SAN policy và keystore nếu mTLS.
3. Quản lý password/truststore/keystore keys qua secret store, không log.
4. Integration test với cert hợp lệ, cert sai, cert hết hạn và rotation.
5. Kiểm tra không có client fallback plaintext khi production bắt buộc TLS.

**Bảo mật CQL không thay bảo mật JMX/OS:** tài khoản Spring Data có `SELECT` không mặc nhiên được chạy `nodetool` hoặc đọc SSTable trên filesystem, và ngược lại.

## 15. Actuator health và metrics: `UP` chưa phải data correctness

Khi thêm `spring-boot-starter-actuator` và có hạ tầng Cassandra phù hợp, Spring Boot có thể cung cấp health indicator cho Cassandra. Tuy nhiên, **health `UP` không đồng nghĩa mọi partition/replica đều đọc/ghi đúng**.

### 15.1. Ba tầng kiểm tra khác nhau

~~~text
Liveness:
  Process/app có thể phục vụ và không kẹt?

Readiness:
  App đã có config, session, schema, role và đủ điều kiện nhận traffic?

Data/functional correctness:
  Query thật theo partition/key/CL, TTL/delete và result mapping đúng?
~~~

Không nên mỗi giây dùng health endpoint để quét một bảng lớn; health check phải **nhẹ, bounded và có deadline**. Với cluster thực, một node còn có thể `UN` trong `nodetool status` nhưng query của partition nóng vẫn chậm do disk/compaction/tombstones.

### 15.2. Dashboard tối thiểu

| Tầng | Metric | Câu hỏi |
| --- | --- | --- |
| **API/Spring** | HTTP p50/p95/p99, request rate, error/timeout, thread pool/queue. | Người dùng chịu ảnh hưởng gì? |
| **Spring Data** | Query name, repository call count, rows returned, mapping errors. | Có N+1 queries hoặc đọc thừa entity không? |
| **Java Driver** | Request latency/errors, retry attempts, connections, in-flight/throttler queue nếu hỗ trợ. | Driver bị queue/routing sai hay backend chậm? |
| **JVM** | Heap/RSS/direct memory, GC pause, CPU, threads. | Mapping/page size/payload gây memory pressure? |
| **Cassandra** | Read/write latency, `tpstats`, compaction, SSTables, tombstones, disk/network. | Replica/coord tắc ở đâu? |
| **Config/security** | Config version, local DC, TLS/auth failures, secret expiry, dependency/SBOM. | Có drift sau deploy hoặc chứng chỉ hết hạn không? |

Khi bật Micrometer/Actuator, **không tự cho rằng mọi metric Driver 4.x được export**: cần dependency/module và wiring metrics đúng version. Không gắn `deviceId`, `eventId`, raw CQL literals hoặc credential vào histogram labels; cardinality và rò rỉ dữ liệu sẽ tăng mạnh.

### 15.3. Quan sát node bằng `nodetool`

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_spring.events_by_device_day
~~~

Các lệnh/metric tùy Cassandra version. `tpstats` pending tasks và disk await tăng cùng p99 có thể gợi ý backend nghẽn; lúc đó tăng pool/timeout từ Spring không giải quyết nguyên nhân vật lý. Tracing có chọn lọc giúp nhìn coordinator/replica cho một CQL; **không bật tracing cho 100% traffic production**.

## 16. Fail-fast khi ứng dụng cấu hình nhầm cluster hoặc datacenter

Một file `application-prod.yml` hợp lệ về cú pháp vẫn có thể trỏ tới **cluster staging**. Khi credentials được chia sẻ hoặc quyền quá rộng, điều đó nguy hiểm hơn lỗi kết nối rõ ràng: ứng dụng có thể đọc/ghi sai dữ liệu mà HTTP vẫn trả 200.

### 16.1. Khai báo nhận dạng cluster kỳ vọng

~~~yaml
# Thêm trong cấu hình môi trường, dùng giá trị thực cấp khi deploy.
app:
  cassandra:
    expected-cluster-name: ${CASSANDRA_EXPECTED_CLUSTER_NAME}
    expected-datacenter: ${CASSANDRA_LOCAL_DC}
~~~

Các thông số trên là **application-defined properties**, không phải cấu hình Cassandra có sẵn của Spring Boot. Có thể viết một startup guard kiểm tra metadata từ Cassandra:

~~~java
// CassandraClusterGuard.java
package example.telemetry;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CassandraClusterGuard implements ApplicationRunner {
    private final CqlSession session;
    private final String expectedName;
    private final String expectedDc;

    public CassandraClusterGuard(
            CqlSession session,
            @Value("${app.cassandra.expected-cluster-name}") String expectedName,
            @Value("${app.cassandra.expected-datacenter}") String expectedDc) {
        this.session = session;
        this.expectedName = expectedName;
        this.expectedDc = expectedDc;
    }

    @Override
    public void run(ApplicationArguments args) {
        Row row = session.execute(
            SimpleStatement.newInstance(
                "SELECT cluster_name, data_center FROM system.local")
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
        ).one();

        if (row == null ||
            !expectedName.equals(row.getString("cluster_name")) ||
            !expectedDc.equals(row.getString("data_center"))) {
            throw new IllegalStateException(
                "Cassandra cluster/DC mismatch; refusing startup");
        }
    }
}
~~~

**Phạm vi test này:**

- `system.local` chứa thông tin của node phản hồi. Kiểm tra một node không thay chứng minh mọi node thuộc đúng topology; phải đối chiếu thêm **driver metadata, DC/rack, release versions và network policy**.
- Startup guard chỉ là một **lớp bảo vệ bổ sung**, không thay IAM/TLS, RBAC và isolation. Nếu service có nhiều DC hoặc failover được duyệt, mô hình kiểm tra cần phản ánh chính sách thực.
- Không log credentials/secret khi phát hiện mismatch. Có thể log expected cluster ID đã được phép và actual metadata ở mức không nhạy cảm.
- Đường đọc `system.local` cần quyền và compatibility thích hợp; xác minh behavior của Cassandra/driver đã chọn.
- Khi fail-fast, readiness phải là failed, **không** tự fallback sang endpoint khác không được phép.

## 17. Phân trang và giới hạn tải khi dùng Spring Data

Một repository trả `List<EventEntity>` có thể tạo cảm giác mọi phần kết quả đã ở RAM và việc đọc vô hại. Trên Cassandra, `LIMIT`, page size, token ranges và dữ liệu có TTL/tombstone chi phối chi phí thực.

### 17.1. LIMIT, page size và HTTP page khác nhau

| Khái niệm | Ý nghĩa | Điều không nên suy |
| --- | --- | --- |
| **CQL `LIMIT 100`** | Số hàng kết quả logic tối đa của statement. | Không có nghĩa replica chỉ đọc 100 cell vật lý. |
| **Java Driver page size** | Số hàng mục tiêu trong một trang native protocol. | Không phải giới hạn byte hay tổng số hàng query. |
| **HTTP page/cursor** | Một đoạn kết quả người dùng nhìn thấy; cursor có thể chứa nhiều trạng thái bucket/query. | Không đồng nghĩa Cassandra có `OFFSET` rẻ như RDBMS. |
| **Cassandra paging state** | Token trạng thái trang được driver/server dùng theo query/protocol. | Không nên dùng như cursor bất biến qua mọi schema/version/deploy. |
| **Time bucket** | Partition `(device_id,event_day)`. | `ORDER BY` trong một bucket không tạo global order xuyên ngày. |

Với API “lấy 50 event mới nhất trong bảy ngày”, service phải quyết định chiến lược **đọc các ngày cần thiết**, chọn ứng viên, merge theo `(event_time,event_id)`, giới hạn số partition/hàng/byte và tạo **cursor theo hợp đồng API**. Không giả định `Pageable` trong Spring Data Cassandra hỗ trợ `OFFSET 100000` với chi phí cố định như cơ sở dữ liệu quan hệ.

### 17.2. N+1 repository calls

~~~java
// PHẢN MẪU nếu devices có hàng nghìn phần tử.
for (String deviceId : deviceIds) {
    // Mỗi device/day là một partition query riêng.
    eventRepository.findWindow(deviceId, day, from, until);
}
~~~

Một loop 10.000 thiết bị có thể tạo **10.000 round-trips CQL**. Nếu gọi async/parallel không giới hạn, nó còn có thể làm coordinator/replica quá tải. Cân nhắc:

- **Bảng theo site/hour** hoặc projection theo query khi endpoint thật sự cần aggregation theo site.
- **Rollup/materialized result** phục vụ thống kê thay vì quét raw events theo mọi device.
- Nếu bắt buộc fan-out, dùng **bounded concurrency** theo app/fleet, deadline, byte/page budgets và backpressure.
- Không chữa bằng `ALLOW FILTERING` hoặc tăng pool/timeout vô hạn.

### 17.3. Spring Data mapping và `SELECT *`

Đọc entity đầy đủ có thể kéo luôn `payload` rất lớn. Nếu endpoint chỉ cần `event_time,event_type`, dùng **CQL projection hẹp** và map DTO/projection thích hợp hoặc tạo bảng summary riêng. Benchmark công bằng cần tách:

1. Chi phí query/network/bytes.
2. Chi phí Spring Data mapping/converter.
3. Chi phí JSON serialization và API response.
4. Chi phí Cassandra server: SSTable/tombstone, disk/compaction/CL.

Không kết luận “Spring Data chậm” khi đối chứng Core API chỉ chọn ít cột hơn; hai đường không thực hiện **cùng công việc**.

## 18. Test cấu hình và repository trước deploy

### 18.1. Ba lớp kiểm thử

| Lớp | Mục đích | Ví dụ |
| --- | --- | --- |
| **Unit/config binding** | Validate property bắt buộc, allowlist environment, defaults và absence of secrets. | Thiếu `CASSANDRA_LOCAL_DC` thì fail startup. |
| **Integration với Cassandra thật/lab** | Kiểm tra CQL schema, entity mapping, CL, auth/TLS, TTL, tombstones và paging. | Save/read key đầy đủ trong một partition ngày. |
| **Load/resilience** | Kiểm tra p95/p99, pool/in-flight, GC, replica down, compaction và multi-DC. | RF=3, `LOCAL_QUORUM`, một replica chậm có kiểm soát. |

Mock repository trong unit test giúp kiểm tra service logic, nhưng **không kiểm tra CQL được phát ra hoặc compatibility native protocol**. Phải có integration test thật với version Cassandra/Driver/Boot được dự kiến.

### 18.2. Ví dụ JUnit với dữ liệu sentinel đã chuẩn bị

Giả định **test environment riêng** đã có keyspace/table và hàng sentinel `device-7` từ mục 6; CI có thể provision bằng Testcontainers hoặc Cassandra lab theo runbook. Ví dụ chỉ là kiểm tra mapping end-to-end:

~~~java
// EventRepositoryIT.java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class EventRepositoryIT {
    @Autowired EventRepository repository;

    @Test
    void readsKnownEventUsingCompositeKey() {
        EventKey key = new EventKey(
            "device-7",
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T09:00:00Z"),
            UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

        EventEntity event = repository.findById(key).orElseThrow();
        assertThat(event.getEventType()).isEqualTo("HEARTBEAT");
        assertThat(event.getPayload()).isEqualTo("ok");
    }
}
~~~

**Để test thực sự độc lập**:

1. CI tạo Cassandra **phiên bản được duyệt** trong mạng cô lập, không dùng contact point production.
2. Chạy DDL/keyspace/schema và seed data **trước khi Spring context cần repository**; khi dùng Testcontainers, cấu hình dynamic properties/service connection đúng phiên bản.
3. Dùng `application-test.yml` với **DC thực của container**, RF phù hợp số node và consistency level test. Cassandra single-node RF=1 không thể thay test quorum RF=3.
4. Bật auth/TLS ở một suite riêng nếu production yêu cầu; kiểm tra role readonly bị từ chối ghi.
5. Xác nhận test đã chạy với **dependency graph thực**, không chỉ mocked `EventRepository`.

### 18.3. Bộ test hành vi bắt buộc

~~~text
[ ] Spring context tạo đúng một CqlSession/mapper/template cần thiết.
[ ] Profile dev/staging/prod/test trỏ đúng cluster/DC, thiếu secret fail-fast.
[ ] Schema/table tồn tại, mapping composite key đúng tất cả 4 thành phần.
[ ] INSERT/SELECT theo CQL partition lookup trả đúng value và event_time.
[ ] Query qua nửa đêm UTC phải đọc hai buckets, không bỏ event.
[ ] Query LIMIT/page nhỏ trả đủ số row theo hợp đồng.
[ ] Kiểm tra null/unset/TTL và xóa không tạo tombstone bất ngờ.
[ ] Read/write timeout và Unavailable không bị đổi thành dữ liệu rỗng.
[ ] Retry write dùng stable key; không tạo UUID ngẫu nhiên mỗi attempt.
[ ] RF=3/LOCAL_QUORUM được test trong topology nhiều replica thật.
[ ] TLS peer/cert/credential/role allow và deny đúng.
[ ] Java Driver core/codec/Spring Data tương thích, không runtime linkage error.
~~~

## 19. Nâng cấp Spring Boot 2.x → 3.x → 4.x: đổi từng lớp có kiểm soát

### 19.1. Khi nâng từ Boot 2.x sang 3.x

Các thay đổi có thể ảnh hưởng nhiều hơn Cassandra:

- Boot 3 yêu cầu **Java 17+** và Spring Framework 6; ứng dụng web/validation/security dùng **`jakarta.*`** thay nhiều API `javax.*` cũ.
- Spring Data Cassandra chuyển từ họ **3.x sang 4.x** theo release train/BOM tương ứng.
- Prefix cấu hình Cassandra **`spring.data.cassandra.*` ở Boot 2.x** có thể phải chuyển sang **`spring.cassandra.*` ở Boot 3.x**; xác minh từng property và effective config.
- Dọn explicit overrides và dependencies transitive cũ; không force một driver jar cũ chỉ để làm các class biến mất “xuất hiện lại”.
- Kiểm tra `CqlSession`, repositories, custom converters, `@PrimaryKeyColumn`, reactive return types và Actuator health.

### 19.2. Khi nâng từ Boot 3.x sang 4.x

Đây là **major migration**: phải đọc release notes/migration guide của bản Boot 4 cụ thể, xác minh Spring Framework 7/Spring Data tương ứng, Java baseline, starter/module names, cấu hình properties, transaction/observability/security APIs và **driver/BOM**. Không tự khẳng định “chỉ đổi `<version>` là đủ” hoặc giữ nguyên toàn bộ property 3.x mà không thử.

### 19.3. Ma trận tương thích cần chốt cho từng lần thay đổi

~~~text
Change ID:
Current Boot exact patch:
Target Boot exact patch:
Spring Framework resolved:
Spring Data Cassandra resolved:
Cassandra Java Driver core resolved:
Mapper/metrics/reactive modules resolved:
JDK build:
Cassandra server source/target version:
Native protocol/feature requirements:
Active contact points and local DC:
Keyspace RF by DC and chosen CL:
Security/TLS/secret references:
Integration/load/recovery tests:
Rollback/restore conditions:
~~~

**Không nâng Cassandra server major và Spring Boot/Driver major cùng lúc** trừ khi có lý do rất rõ và rollback/recovery plan đã được diễn tập. Tách thay đổi giúp khoanh vùng lỗi và tránh trạng thái binary/SSTable/schema không tương thích sau upgrade.

## 20. Chẩn đoán các lỗi quen thuộc sau khi thêm starter

| Triệu chứng | Giả thuyết hợp lý | Kiểm tra/khắc phục |
| --- | --- | --- |
| Spring không tạo `CqlSession` bean | Thiếu starter, auto-config bị exclude, bean custom hoặc điều kiện classpath khác. | Xem condition evaluation report, dependency tree và bean graph. |
| `NoHostAvailable`/session init thất bại | Contact points sai, port/firewall, DC metadata, TLS/auth hoặc node down. | Kiểm tra network, local DC, handshake và node status. |
| `AuthenticationException` | Cluster bật auth, credential/role/secret sai. | Kiểm tra auth provider, secret version, credential rotation; không chuyển superuser. |
| `Unauthorized` khi SELECT | Role thiếu quyền bảng/keyspace. | Cấp `GRANT SELECT` tối thiểu, test allow/deny. |
| Query báo table/keyspace không tồn tại | Keyspace mặc định hoặc schema migration chưa chạy, identifier sai. | `DESCRIBE KEYSPACE/TABLE`, so entity/table mapping. |
| Repository mapping exception | Type `timestamp/date/uuid` không khớp, cột đổi tên, UDT/codec drift. | So CQL schema và Java mapping, integration test. |
| `NoSuchMethodError`/linkage error | Version Spring Data/Driver/codec không thống nhất do override/transitive conflict. | Xem **resolved dependency graph**; trở lại BOM/version được hỗ trợ. |
| Profile prod vẫn kết nối dev | Sai `spring.profiles.active`, properties precedence hoặc env fallback. | Fail-fast expected cluster/DC, audit effective config đã redact. |
| `LOCAL_QUORUM` báo `Unavailable` trên lab một node | RF/replica count không tương thích. | Tạo test topology đúng hoặc chọn RF/CL test có chủ đích, không kết luận driver hỏng. |
| p99 tăng khi thêm repository | Query projection, N+1, paging, TTL/tombstones hoặc mapping/GC. | So CQL thật và bytes, đo client/server, thử Core full/narrow công bằng. |
| App báo `UP` nhưng endpoint timeout | Health query quá hẹp, partition nóng/replica chậm. | Functional canary, partition metrics, latency/compaction/GC. |
| Write timeout rồi dữ liệu trùng | Retry sinh event ID mới hoặc mutation không idempotent. | Stable key, durable retry/reconciliation và timestamp/TTL policy. |

### 20.1. Debug có thứ tự

~~~mermaid
flowchart TD
    A["Spring Boot Cassandra lỗi"] --> B{"Không tạo được CqlSession?"}
    B -->|Có| C["Starter/BOM, properties, TLS/auth, DC/contact points"]
    B -->|Không| D{"Repository/mapper/CQL error?"}
    D -->|Có| E["CQL schema, @PrimaryKey, converters, driver version"]
    D -->|Không| F["Đo API/driver p99, queue, retries, rows/bytes"]
    F --> G{"Replica/compaction/disk/tombstone nghẽn?"}
    G -->|Có| H["Sửa data model, giảm tải, storage/repair theo runbook"]
    G -->|Không| I["Kiểm tra mapping/GC, query fan-out, network/TLS"]
    C --> J["Integration test + canary"]
    E --> J
    H --> J
    I --> J
    J --> K{"SLO, security và correctness đạt?"}
    K -->|Không| L["Rollback config/artifact có kiểm soát"]
    K -->|Có| M["Triển khai dần, ghi bằng chứng"]
~~~

## 21. Cấu hình có hiệu lực: YAML hợp lệ không có nghĩa Driver đã nhận giá trị

Một dự án có thể chứa ba nguồn thiết lập:

1. `application.yml`, `application-*.yml`, system properties, environment variables, Config Server/secret store của **Spring Boot**.
2. `application.conf`/HOCON và `DriverConfigLoader` của **Java Driver**.
3. Các `@Bean` customizer, `CqlSessionBuilder` hoặc `CqlSession` do ứng dụng tự tạo.

Không nên dự đoán thứ tự thắng thua của mọi option chỉ bằng cách nhìn một file. Tùy version và việc có customizer, một property có thể đã được Boot translate sang driver option, một property khác có thể bị custom loader ghi đè. **Cần một nguồn cấu hình được quy định cho từng option và một test xác minh effective runtime value.**

### 21.1. Ma trận ownership cấu hình

| Thông số | Chủ sở hữu khuyến nghị | Cách xác minh |
| --- | --- | --- |
| Expected cluster/environment | Deployment config và startup guard ứng dụng. | So `system.local`/driver metadata, readiness fail khi mismatch. |
| Contact points, port, local DC | Spring Boot Cassandra properties **theo version**. | Connection diagnostics, metadata DC và network policy. |
| Keyspace name | Spring Boot + DDL provisioning. | Query schema và entity mapping, không auto-create prod. |
| Username/secret reference | Secret management/Boot external config. | Auth test, rotate rehearsal, không log giá trị bí mật. |
| TLS/trust/hostname policy | Security config qua cơ chế Boot/Driver được hỗ trợ. | Test CA/cert/hostname đúng và sai. |
| Request CL, timeout, page size | Một policy rõ ràng: Boot hoặc driver profile. | Effective driver config, query canary và request tracing. |
| Pool/throttler/retry | Driver config/profile có version pin. | Driver metrics/queue, overload tests. |
| RBAC/replication/schema | Cassandra cluster/DDL migrations. | `DESCRIBE`, role allow/deny, nodetool và CQL tests. |

### 21.2. Không echo secrets khi debug

Chỉ log các giá trị không nhạy cảm ở mức cần thiết, ví dụ:

~~~text
service              = telemetry-api
environment          = staging
boot_version         = <resolved-version>
spring_data_version  = <resolved-version>
driver_core_version  = <resolved-version>
config_revision      = git:abcdef12
expected_cluster_id  = cassandra-staging
local_dc             = dc1
keyspace             = telemetry_spring
tls_required         = true
request_profile      = interactive
~~~

**Không log:** password, private key, token, nguyên vẹn truststore/keystore, raw payload hoặc CQL có literal dữ liệu người dùng. Endpoint Actuator về cấu hình cũng phải được bảo vệ và che giá trị nhạy cảm; không public toàn bộ `/actuator/env` hoặc `/actuator/configprops`.

### 21.3. Quy trình kiểm tra khi migrate property

Khi đổi `spring.data.cassandra.*` sang `spring.cassandra.*`:

1. Lập danh sách toàn bộ khóa config hiện tại, **không đọc tràn lan production secrets**.
2. Đối chiếu tên/kiểu/default/đơn vị của từng khóa với **configuration metadata phiên bản Boot mới**.
3. Tạo cấu hình test thiếu một biến bắt buộc và xác minh app **fail-fast**.
4. Tạo test với `local-datacenter` sai, xác nhận app **không lặng lẽ** chấp nhận sai cluster.
5. So effective request timeout, CL, page size, auth/TLS và bean graph với baseline.
6. Load test có dữ liệu giống workload, thay đổi ít nhất một biến mỗi lần, canary và rollback.

**Migration helper** (nếu Spring Boot cung cấp ở version tương ứng) chỉ giúp tìm một số property đã đổi tên; nó không thay test behavioral compatibility, và không nên giữ helper tạm thời như dependency production vô hạn.

## 22. Case study: phụ thuộc bị override và truy vấn đột nhiên lỗi

### 22.1. Bối cảnh giả lập

Ứng dụng chạy Boot 3.x với BOM quản lý Spring Data Cassandra và Java Driver. Một thư viện nội bộ yêu cầu tính năng Driver khác, nên developer force `java-driver-core` một patch mới, nhưng **không đồng bộ** các module Driver đi kèm. CI build thành công, nhưng một endpoint dùng custom codec/mapper gặp lỗi `NoSuchMethodError` khi có traffic.

| Mốc | Quan sát | Giải thích cần kiểm chứng |
| --- | --- | --- |
| T0 | POM chỉ đổi một dòng version Driver. | Build graph có thể còn nhiều module driver khác version. |
| T1 | Unit tests mock repository đều xanh. | Mock không load đầy đủ native driver/codec runtime. |
| T2 | Spring Boot application context khởi động. | Không chứng minh mọi query/codec path đã thực thi. |
| T3 | Endpoint `GET /events` lỗi linkage trên một data shape hiếm. | Có thể version mismatch hoặc mapping với API mới/cũ. |
| T4 | Developer tăng Cassandra request timeout. | Không thể sửa lỗi JVM method linkage. |

### 22.2. Hướng điều tra đúng

1. Ghi **stack trace/class lỗi**, không đưa CQL literal nhạy cảm vào log.
2. Kiểm tra **resolved runtime dependency tree/SBOM**, không chỉ dependencies được khai báo trực tiếp.
3. So module `java-driver-core`, mapper/metrics/reactive modules và Spring Data Cassandra theo **BOM của patch Boot đang chạy**.
4. Thử bỏ override để trở lại bộ dependency đã được BOM pin; nếu bắt buộc override vì bảo mật, chọn **bộ artifact tương thích** và chạy integration tests.
5. Test startup, CQL/codec/custom types, auth/TLS, paging và load trên staging gần production.
6. Canary một nhóm pod, theo dõi errors/p99; rollback artifact nếu regression.

**Không kết luận mọi `NoSuchMethodError` đều do Driver**, vì có thể liên quan Spring Framework/Reactor/Jackson/extension khác. Nhưng khi vừa thay dependency, giải pháp đầu tiên là **xác định classpath/runtime linkage có thực**, không tăng Cassandra pool hoặc thêm retries.

### 22.3. Case khác: Boot chạy lên nhưng repository đọc sai keyspace

Một service staging có `application.yml` chứa `spring.cassandra.keyspace-name=telemetry_spring`, nhưng code custom tạo `CqlSession` khác có default keyspace riêng; Spring Data dùng session của Boot, custom DAO dùng session khác. Một đường trả dữ liệu đúng, đường kia báo table không tồn tại.

**Cách sửa:** gom cấu hình dưới một **session/identity được Spring quản lý**, dùng **tên bảng fully qualified trong CQL cần phân biệt**, kiểm tra bean graph, expected cluster/DC và role. Không “sửa” bằng cách thêm `USE` hay tự tạo session mới ở mỗi request.

## 23. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Hướng đúng |
| --- | --- | --- |
| Copy `spring.data.cassandra.*` từ Boot 2.x sang 3.x mà không kiểm tra. | Property có thể không bind đúng; runtime dùng default sai. | Đối chiếu configuration metadata theo version và test effective config. |
| Gán `<version>` tùy ý cho Spring Data và Driver khi đã dùng Boot BOM. | Dependency drift và runtime linkage/codec bugs. | Ưu tiên BOM; override có mục tiêu và integration tests. |
| Hiểu Spring Data 4.4 nghĩa Cassandra server 4.4. | Chọn sai server/Driver support matrix. | Tách bốn trục version: Boot, Data, Driver, server. |
| Cấu hình `local-datacenter` bằng cloud region tùy ý. | Routing/connection sai DC. | Dùng tên DC của snitch metadata. |
| Dùng một node lab, RF=3 rồi kỳ vọng `LOCAL_QUORUM` chịu node down. | Không đủ natural replicas thực. | Test topology/CL đúng, phân biệt RF lab và production. |
| Một lần `repository.save` được coi là transaction multi-table. | Partial writes/data drift. | Durable mutation log/CDC/reconciliation. |
| Lấy `@Table` là đủ để tạo bảng production. | Missing schema hoặc schema drift. | Schema migration có version riêng, role riêng. |
| Derived repository query tự động tối ưu mọi `WHERE`. | Thiếu partition key, scan hoặc query bị reject. | Thiết kế bảng theo query và kiểm CQL phát ra. |
| `findAll()` trả hàng triệu entity rồi lọc ở Java. | I/O, heap, GC và p99 tăng. | Partition/range lookup, rollup hoặc projection có giới hạn. |
| `LIMIT 100` nghĩa server đọc đúng tối đa 100 cells. | Bỏ qua chi phí tombstone/SSTable scan. | Benchmark server read cost, TTL/delete/compaction. |
| Reactive `Flux` dùng `block()` trong Netty event-loop. | Mất lợi ích nonblocking, nghẽn event loop. | Reactive end-to-end hoặc bounded scheduler riêng. |
| Tạo `CqlSession` mới cho mỗi request trong Spring Boot. | Connection churn, TLS/auth/metadata cost. | Inject singleton/managed session. |
| App tự `DROP/CREATE` schema khi restart. | Nguy cơ mất dữ liệu/race và quyền ứng dụng quá rộng. | Migration pipeline với approval/backup/rollback. |
| Dùng credential production trong dev và bỏ TLS verification. | Lộ dữ liệu, khó tách blast radius. | Identity/TLS/secrets theo môi trường. |
| Xem Actuator `UP` là bằng chứng mọi replica/quorum khỏe. | Bỏ qua hot partitions và dữ liệu sai. | Functional canary + server metrics + correctness tests. |
| Tăng timeout để chữa `NoSuchMethodError` hoặc `Unauthorized`. | Che nguyên nhân, không sửa lỗi. | Phân loại JVM/classpath, auth và Cassandra failure đúng. |

## 24. Bài tập tự kiểm tra có đáp án

**Bài 1.** Spring Boot 3.x ứng dụng cấu hình `spring.data.cassandra.contact-points` theo hướng dẫn Boot 2.x và app không kết nối như dự kiến. Bước kiểm tra quan trọng nhất?

**Đáp án:** Kiểm tra **configuration metadata/prefix của Boot patch đang dùng**, thường là `spring.cassandra.*` trên Boot 3.x, rồi xác minh effective contact points, local DC và bean graph. Không chỉ tăng timeout.

**Bài 2.** Spring Boot 3.4.x và Spring Data Cassandra 4.4.x có nghĩa Cassandra cluster phải chạy server 4.4.x?

**Đáp án:** **Không.** Version Spring Data là thư viện Java; server Cassandra là dự án khác. Chọn theo driver/native protocol support matrix và yêu cầu features/schema.

**Bài 3.** Một developer nâng riêng `java-driver-core` nhưng để module mapper/metrics cũ, rồi thấy `NoSuchMethodError`. Phải điều tra thế nào?

**Đáp án:** Kiểm tra **resolved dependency graph/SBOM**, BOM Boot, bộ module Driver cùng họ và Spring Data; bỏ/điều chỉnh override sau khi kiểm chứng, chạy integration tests. Không xem đó là lỗi Cassandra compaction mặc định.

**Bài 4.** Tại sao cấu hình `spring.cassandra.local-datacenter` không thể chỉ điền tên region cloud?

**Đáp án:** Driver cần **tên datacenter mà cluster/snitch báo**, không phải một chuỗi region tùy ý. Sai DC có thể khiến node bị loại khỏi local routing hoặc tăng cross-DC latency.

**Bài 5.** Với `PRIMARY KEY ((device_id,event_day),event_time,event_id)`, một `@PrimaryKeyClass` chỉ đánh dấu `device_id` là partition key. Mapping đã đúng?

**Đáp án:** **Chưa.** `event_day` là thành phần thứ hai của partition key; `event_time,event_id` là clustering columns. Ordinal/type phải khớp DDL thực.

**Bài 6.** Một API cần sự kiện từ 23:45 UTC ngày 20/11 tới 00:15 UTC ngày 21/11. Service gọi `findWindow` cho ngày 20/11 và trả kết quả. Thiếu gì?

**Đáp án:** Phải đọc **cả bucket ngày 21/11**, merge theo thời gian/tie-breaker, áp global limit/pagination và giới hạn fan-out. Một query với `event_day` cố định chỉ đọc một partition ngày.

**Bài 7.** Với RF=3 và `LOCAL_QUORUM` tại `dc1`, cần bao nhiêu full replicas phản hồi?

**Đáp án:** **Hai**. Điều này không chứng minh mọi replica đều đã đồng bộ, cũng không thay repair.

**Bài 8.** Một staging cluster chỉ có một node nhưng keyspace RF=3, client dùng `LOCAL_QUORUM`. Vì sao test có thể lỗi?

**Đáp án:** Số full replica khả dụng không đủ quorum yêu cầu. Dùng topology thật cho resilience test hoặc điều chỉnh RF/CL của lab một cách có chủ đích, không tùy tiện hạ consistency của production.

**Bài 9.** `repository.save` một entity chỉ đọc hai cột, các trường khác `null`. Nó có chắc chỉ cập nhật hai cột ấy không?

**Đáp án:** **Không chắc.** Null có thể được lưu thành tombstone hoặc bị bỏ qua tùy Spring Data mapping/configuration. Dùng statement update đúng cột hoặc kiểm chứng null/unset strategy trước khi ghi.

**Bài 10.** Spring Data Cassandra repository có transaction/dirty checking như JPA Hibernate không?

**Đáp án:** **Không mặc định.** Cassandra có mutation/batch/LWT semantics riêng; sửa Java object không tự cập nhật DB và nhiều bảng không trở thành transaction ACID kiểu quan hệ chỉ vì dùng repository.

**Bài 11.** `CassandraRepository.findAll()` trả hàng triệu rows, app gọi `stream().filter(...)` sau khi load. Điều gì không ổn?

**Đáp án:** Cassandra có thể phải quét/truyền rất nhiều partition/bytes; ứng dụng giữ entity và gây GC. Thiết kế **bảng theo truy vấn**, full partition key và clustering range/limit.

**Bài 12.** Spring Boot tự có một `CqlSession`. Service lại tạo thêm một session mỗi HTTP request. Rủi ro?

**Đáp án:** Connection churn, metadata/TLS/auth overhead và các đường CQL có config khác nhau. Inject `CqlSession` quản lý bởi Spring; chỉ tạo nhiều session nếu thật sự cần nhiều logical clusters/identities.

**Bài 13.** `/actuator/health` trả UP nhưng API đọc một partition nóng p99 8 giây. Có mâu thuẫn không?

**Đáp án:** **Không.** Health có thể chỉ kiểm kết nối/query nhẹ, còn partition cụ thể chịu disk/tombstone/compaction/GC. Cần query canary theo workload và metrics cả client/replica.

**Bài 14.** Thêm `spring-boot-starter-data-cassandra-reactive` có làm mọi repository blocking tự trở thành reactive và CQL tự nhanh hơn?

**Đáp án:** **Không.** Phải dùng reactive repository/template đúng version, không block event-loop, quản lý demand/concurrency. Server query cost vẫn theo data model, CL và tài nguyên.

**Bài 15.** Vì sao `application-prod.yml` không nên chứa password Cassandra và `local-datacenter` fallback về dev?

**Đáp án:** Secret có thể bị lộ trong source, còn fallback môi trường sai có thể truy cập nhầm cluster/DC. Dùng secret manager, fail-fast, startup guard, TLS/role riêng theo môi trường.

**Bài 16.** Test unit mock `EventRepository` xanh sau khi nâng Boot/Driver. Đã chứng minh native protocol/mapper/DDL tương thích?

**Đáp án:** **Chưa.** Mock không kết nối Cassandra. Cần integration tests với cluster/version/schema thật hoặc container cô lập, CQL/CL/auth/TLS, paging và failure modes.

**Bài 17.** API chỉ cần `event_time,event_type` nhưng repository đọc cả `payload` 200 KiB/hàng. Giải pháp đầu tiên nên xem?

**Đáp án:** Giảm **column projection/bytes** qua CQL/DTO hoặc bảng summary theo truy vấn, rồi benchmark. Đổi thư viện mapping mà vẫn SELECT payload lớn có thể không giải quyết nút thắt.

**Bài 18.** Team muốn đổi partition key từ `device_id` sang `(device_id,event_day)` bằng cách sửa `@PrimaryKeyClass` rồi deploy. Đã đủ chưa?

**Đáp án:** **Không.** Partition key quyết định token/replicas và schema CQL. Phải tạo bảng mới, backfill/catch-up mutation, xử lý TTL/delete, reconcile và canary/rollback theo quy trình.

## 25. Checklist vận hành và sơ đồ quyết định

~~~text
VERSION / DEPENDENCY
[ ] Chọn bản Spring Boot patch được hỗ trợ, ghi JDK chính xác.
[ ] Theo BOM, ghi Spring Data Cassandra, Java Driver và module resolved.
[ ] Không force từng artifact khi chưa có compatibility test.
[ ] Kiểm tra migration guide khi đổi Boot 2.x -> 3.x -> 4.x.
[ ] Cassandra server/native protocol/feature support được xác minh.

CQL / DATA MODEL
[ ] Keyspace NTS/RF theo DC, bảng/projection đúng query shape.
[ ] Composite partition/clustering key trong @PrimaryKeyClass khớp CQL.
[ ] event_day được tính thống nhất UTC và bound time window.
[ ] LIMIT/column projection/page/byte budgets và fan-out có giới hạn.
[ ] Schema migrations không được chạy bằng role ứng dụng production.

SPRING / SESSION
[ ] Đúng starter blocking hoặc reactive cho kiểu ứng dụng.
[ ] application.yml profile đúng version, không còn property cũ bị bỏ qua.
[ ] Một CqlSession được Spring quản lý cho logical cluster/identity.
[ ] Inject repository/template/session, không tạo session theo request.
[ ] Effective local DC, CL, timeout, throttler và page size được xác nhận.

SECURITY / ENVIRONMENT
[ ] Dev/staging/prod tách cluster, role, network, secrets, certificate/CA.
[ ] TLS server peer validation được bật theo policy; không trust-all.
[ ] Credential/secret manager có rotation và fail-closed.
[ ] App không dùng superuser; CQL RBAC và tenant authorization đúng.
[ ] Startup guard từ chối expected cluster/DC mismatch.

TEST / OBSERVABILITY / RELEASE
[ ] Integration test chạy với Cassandra thực và schema đã provision.
[ ] RF/CL, TTL/delete, null/unset, paging, large payload được test.
[ ] Test startup failure, auth/TLS failure và dependency linkage error.
[ ] API p95/p99, driver in-flight/retry/queue, JVM GC, disk/compaction được đo.
[ ] Actuator health không thay functional canary/data correctness test.
[ ] Canary theo nhóm instance, có stop criteria và rollback artifact/config.
~~~

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot cần Cassandra"] --> B["Chọn Boot/JDK và dùng BOM"]
    B --> C["Kiểm tra Spring Data + Driver + server compatibility"]
    C --> D["Tạo keyspace/bảng theo query, RF/DC và CL"]
    D --> E["Cấu hình spring.cassandra.*, TLS, roles và Spring profiles"]
    E --> F["Map @PrimaryKeyClass/@Table + Repository/Template"]
    F --> G["Dùng CqlSession managed cho CQL chuyên biệt nếu cần"]
    G --> H["Integration test, dependency graph, paging, auth và failover"]
    H --> I{"Correctness + SLO + security đạt?"}
    I -->|Chưa| J["Sửa version/config/query/permission, test lại"]
    J --> C
    I -->|Đạt| K["Canary production và theo dõi JVM/driver/replica"]
    K --> L["Giữ rollback, mở rộng rollout khi ổn định"]
~~~

**Tổng kết:** tích hợp Cassandra trong Spring Boot cần phối hợp **Spring Boot BOM, Spring Data Cassandra, Java Driver và phiên bản Cassandra server**, thay vì chỉ thêm một starter rồi chỉnh contact point. Trên Boot 3.x, cấu hình thường qua **`spring.cassandra.*`**, nên tách dev/staging/prod, xác minh local DC, TLS, secrets, RF/CL và quản lý một `CqlSession` sống lâu. `CassandraRepository`/`CassandraTemplate` giảm boilerplate nhưng **không thay partition key, clustering key, TTL/tombstone, quorum, repair hoặc chi phí query**. Ma trận phiên bản là bước định hướng; **BOM/resolved dependency graph và integration tests của đúng bản patch mới là bằng chứng tương thích**. Triển khai an toàn luôn cần schema có version, kiểm tra correctness, giám sát p99/tài nguyên, canary và phương án rollback rõ ràng.
