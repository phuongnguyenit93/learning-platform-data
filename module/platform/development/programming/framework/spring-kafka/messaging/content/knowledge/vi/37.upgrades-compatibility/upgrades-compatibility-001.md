# Theo dõi ma trận phiên bản Spring Kafka

Một ứng dụng Spring Kafka không chỉ có một phiên bản cần theo dõi. Runtime thực tế là tổ hợp của JDK, Spring Boot, Spring Framework, Spring Kafka, Kafka client, Kafka broker và đôi khi cả Kafka Streams, serializer hoặc Schema Registry. Một dependency nâng cấp riêng lẻ có thể làm thay đổi API, hành vi retry, transaction, serialization hoặc giao thức kết nối dù mã nguồn ứng dụng không đổi.

Ma trận phiên bản (compatibility matrix) ghi lại tổ hợp đã được xác minh, môi trường đang chạy, nguồn xác nhận và kết quả kiểm thử. Nó giúp đội phát triển biết tổ hợp nào được hỗ trợ, tổ hợp nào chỉ tương thích về giao thức và tổ hợp nào đã thực sự được ứng dụng kiểm thử. Ma trận phải là dữ liệu vận hành có owner và ngày cập nhật, không chỉ là một bảng version được chép từ README.

Bài học thuộc chương **Nâng cấp và tương thích** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Vì sao cần theo dõi ma trận phiên bản?

Một hệ thống Kafka có nhiều lớp phần mềm được phát hành độc lập. Ví dụ, ứng dụng có thể dùng Spring Boot quản lý dependency, Spring Kafka cung cấp listener container và template, Kafka client thực hiện protocol, còn broker do một đội nền tảng vận hành.

Nếu chỉ ghi “ứng dụng dùng Spring Kafka 3.x”, đội vận hành vẫn chưa biết:

- Spring Boot và Spring Framework đang ở phiên bản nào.
- Kafka client thực tế được resolve từ dependency tree là phiên bản nào.
- Kafka broker cluster đang chạy phiên bản nào và đang trong giai đoạn rolling upgrade hay không.
- JDK runtime và JDK build có đáp ứng yêu cầu của từng thành phần không.
- `spring-kafka-test`, Kafka Streams, serializer và Schema Registry client có cùng tổ hợp tương thích không.
- Tổ hợp đó đã được kiểm thử trong môi trường production-like hay chỉ mới build thành công.

Ma trận trả lời các câu hỏi này tại một thời điểm cụ thể. Khi một thành phần thay đổi, đội có thể xác định những thành phần cần đánh giá lại và kiểm thử.

## 2. Các lớp phiên bản trong một ứng dụng Spring Kafka

Một ma trận tối thiểu nên theo dõi các lớp sau:

| Thành phần | Vai trò | Cần xác minh |
| --- | --- | --- |
| JDK | Runtime và compiler | Phiên bản Java tối thiểu/tối đa được framework hỗ trợ |
| Spring Boot | Application platform và dependency management | Spring Framework, Spring Kafka và dependency versions được quản lý |
| Spring Framework | Container, transaction, lifecycle, AOP | Phiên bản tương thích với Boot và thư viện tích hợp |
| Spring Kafka | `KafkaTemplate`, listener container, error handling | API, behavior và Kafka client range |
| `kafka-clients` | Producer, consumer, AdminClient và protocol | Phiên bản được resolve, broker compatibility và feature support |
| Kafka broker | Lưu trữ, replication, group coordinator, transactions | Cluster version, rolling-upgrade state và broker configuration |
| Kafka Streams | Stream processing API/runtime nếu ứng dụng dùng | Cùng dòng Kafka client và compatibility của state store |
| Serializer/Schema Registry | Chuyển đổi event và quản lý schema | Wire format, serializer API và server compatibility |
| `spring-kafka-test` | Embedded Kafka và test utilities | Cùng dòng version với Spring Kafka runtime |
| Build tool/plugin | Compile, test, packaging | Maven/Gradle và plugin hỗ trợ JDK hiện tại |

Không phải ứng dụng nào cũng dùng Kafka Streams hoặc Schema Registry. Hãy đánh dấu thành phần không áp dụng thay vì bỏ trống không rõ nghĩa.

## 3. Tương thích không đồng nghĩa với cùng phiên bản

Các thành phần không cần có cùng số phiên bản. Spring Boot quản lý một tập dependency đã được tích hợp; Spring Kafka phụ thuộc Kafka client; Kafka client giao tiếp với broker qua protocol có khả năng tương thích theo quy tắc của Kafka.

Ví dụ, số phiên bản Spring Kafka và Kafka broker không nhất thiết giống nhau. Một Kafka client mới có thể kết nối broker cũ trong phạm vi protocol được hỗ trợ, nhưng tính năng mới có thể cần broker mới. Tương tự, ứng dụng compile thành công không chứng minh mọi đường chạy runtime đều hoạt động.

Cần phân biệt:

- **Build compatibility:** dependency resolve và mã nguồn compile được.
- **API compatibility:** class/method mà ứng dụng gọi còn tồn tại và giữ semantics cần thiết.
- **Protocol compatibility:** client và broker trao đổi được request/response.
- **Feature compatibility:** tính năng cụ thể được hỗ trợ ở cả client, broker và cấu hình.
- **Operational compatibility:** workload thật chạy ổn định, có thể quan sát, nâng cấp và rollback.

Một tổ hợp chỉ được ghi là verified khi các mức cần thiết cho workload đã được kiểm tra.

## 4. Nguồn chuẩn để xác minh phiên bản

Không lấy ma trận từ một blog hoặc một bảng không ghi ngày cập nhật. Xác minh theo tài liệu chính thức của từng thành phần:

| Câu hỏi | Nguồn cần kiểm tra |
| --- | --- |
| Spring Boot hỗ trợ JDK nào? | System Requirements và release notes của Spring Boot |
| Boot quản lý Spring Framework và Spring Kafka version nào? | Dependency Versions appendix/BOM của đúng Spring Boot release |
| Spring Kafka hỗ trợ API và Kafka client nào? | Spring for Apache Kafka reference, release notes và dependency metadata |
| Kafka client hỗ trợ broker/protocol nào? | Apache Kafka documentation và release/upgrade notes |
| Kafka broker upgrade theo thứ tự nào? | Apache Kafka upgrade guide của source và target release |
| Serializer/Schema Registry có tương thích không? | Tài liệu chính thức của serializer và Schema Registry vendor |
| JDK runtime có hỗ trợ không? | JDK vendor support matrix và yêu cầu của framework |

Khi ghi một quyết định vào ma trận, lưu URL hoặc tên tài liệu, phiên bản tài liệu, ngày kiểm tra và người xác minh. Release notes thường chứa các thay đổi không thể suy ra từ số version, như deprecation, default behavior và giới hạn tương thích.

## 5. Spring Boot BOM là điểm xuất phát của dependency versions

Trong dự án Spring Boot, nên để Spring Boot dependency management quản lý các dependency Spring và Kafka tương ứng, trừ khi có quyết định nâng cấp độc lập đã được kiểm chứng.

Ví dụ Maven dùng Spring Boot parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Placeholder `BOOT_VERSION` được cung cấp trong project properties hoặc version catalog của tổ chức. Không chép một con số version minh họa vào production mà chưa đối chiếu release được chọn.

Nếu dự án import `spring-boot-dependencies` BOM thay vì dùng parent, bảo đảm BOM được import đúng scope và thứ tự ưu tiên. Dependency không có version sẽ lấy version do dependency management cung cấp.

## 6. Quản lý dependency bằng Gradle

Với Gradle, có thể dùng Spring Boot plugin cùng dependency management hoặc import platform BOM:

~~~kotlin
val bootVersion = providers.gradleProperty("springBootVersion").get()

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:$bootVersion"))
    implementation("org.springframework.kafka:spring-kafka")
    testImplementation("org.springframework.kafka:spring-kafka-test")
}
~~~

Nếu project đã dùng Spring Boot Gradle plugin và dependency management, tránh khai báo BOM trùng lặp không cần thiết. Chọn một cơ chế quản lý version nhất quán.

Không đặt version `spring-kafka`, `kafka-clients` và `spring-kafka-test` độc lập một cách tùy tiện. Nếu buộc override một thành phần, ghi lý do, nguồn xác minh và test bắt buộc vào compatibility record.

## 7. Xác minh dependency thực tế được resolve

File build chỉ thể hiện khai báo trực tiếp. Dependency bắc cầu, BOM, plugin hoặc constraint có thể khiến version runtime khác dự kiến.

Maven:

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.kafka:*,org.apache.kafka:*
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency kafka-clients \
  --configuration runtimeClasspath
~~~

Cần kiểm tra cả `compileClasspath`, `runtimeClasspath` và test classpath khi chúng khác nhau. Lưu output dependency tree của release candidate để đối chiếu với bản đã triển khai.

Nếu dependency tree có nhiều version hoặc version bị force, tìm dependency nào kéo version đó vào. Không giải quyết conflict bằng cách exclude ngẫu nhiên vì có thể bỏ mất class hoặc API mà thư viện khác cần.

## 8. Spring Boot, Spring Framework và Spring Kafka

Spring Boot release được xây dựng quanh một dòng Spring Framework và một tập dependency đã được kiểm tra cùng nhau. Khi nâng Boot, cần đọc release notes để biết thay đổi ở Framework, auto-configuration, property binding, logging, Jackson và transaction.

Spring Kafka tích hợp sâu với Spring container, bean lifecycle, transaction manager và observation. Vì vậy, version Spring Kafka không chỉ là một thư viện producer/consumer độc lập. API của listener container, error handler, message conversion và transaction integration có thể thay đổi giữa các dòng.

Quy trình chọn version:

1. Chọn Spring Boot target dựa trên chính sách hỗ trợ JDK và ứng dụng.
2. Đọc dependency versions của Boot target để biết Spring Framework và Spring Kafka được quản lý.
3. Kiểm tra Spring Kafka release notes và migration guide.
4. Xác minh Kafka client version được resolve.
5. Kiểm tra broker và feature requirements.
6. Chạy compile, test và integration test trước khi rollout.

Không nâng Spring Framework riêng lẻ khỏi dòng Boot đang quản lý nếu chưa có lý do và ma trận hỗ trợ rõ ràng.

## 9. Spring Kafka và kafka-clients

Spring Kafka cung cấp abstraction như `KafkaTemplate`, `@KafkaListener`, listener container, message conversion, error handler và transaction integration. Thực thi protocol nằm trong Apache Kafka Java client, artifact thường là `kafka-clients`.

Một số API Spring Kafka gọi trực tiếp API Kafka client. Vì vậy, override Kafka client quá cũ hoặc quá mới có thể tạo lỗi compile/runtime như `NoSuchMethodError`, `ClassNotFoundException` hoặc hành vi khác với version mà Spring Kafka đã kiểm thử.

Theo dõi ít nhất:

- Spring Kafka version.
- Resolved `kafka-clients` version.
- Kafka broker version theo từng cluster.
- Kafka client config có sử dụng tính năng mới không.
- Release note có thay đổi default hoặc deprecation không.

Không giả định version Kafka client phải trùng version broker. Đọc compatibility guidance và kiểm thử đúng broker target.

## 10. Kafka client và broker compatibility

Kafka client và broker có cơ chế thương lượng API version trong phạm vi hỗ trợ, nhưng không phải mọi feature đều khả dụng trên mọi tổ hợp.

Khi kiểm tra tương thích, cần phân biệt:

- Client có kết nối và thực hiện request cơ bản được không?
- Broker có hỗ trợ API version cần cho feature không?
- Feature có cần broker configuration hoặc cluster metadata mới không?
- Cluster đang rolling upgrade có broker ở nhiều version; client có hoạt động với toàn bộ broker trong giai đoạn chuyển tiếp không?
- Transaction, idempotent producer, group protocol, topic administration hoặc quota behavior có thay đổi không?

Ví dụ, một ứng dụng dùng transaction cần xác minh producer transaction API, broker support, transaction coordinator và cấu hình transactional ID. Chỉ test gửi record không transactional không đủ chứng minh transaction hoạt động.

Khi cluster có nhiều broker version trong rolling upgrade, hãy kiểm tra cả giai đoạn mixed-version và trạng thái sau nâng cấp. Tuân thủ thứ tự upgrade và inter-broker protocol guidance của Kafka release tương ứng.

## 11. Theo dõi JDK và bytecode target

JDK build, JDK test và JDK runtime có thể khác nhau. Ma trận nên ghi rõ:

- JDK dùng trên developer workstation/CI.
- Java toolchain/compiler release.
- Bytecode target.
- JDK chạy container production.
- JDK được Spring Boot và thư viện liên quan hỗ trợ.
- JDK vendor/distribution nếu tổ chức có chuẩn riêng.

Ví dụ Gradle toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Ví dụ Maven compiler release:

~~~xml
<properties>
    <maven.compiler.release>JAVA_RELEASE</maven.compiler.release>
</properties>
~~~

Các giá trị chỉ minh họa cách khai báo. Chọn JDK dựa trên yêu cầu của Boot target và chính sách runtime. Compile bằng JDK mới hơn không tự chứng minh ứng dụng chạy được trên JDK thấp hơn; bytecode target, API được gọi và dependency runtime đều phải phù hợp.

## 12. Kafka Streams, serializer và Schema Registry

Nếu module dùng Kafka Streams, theo dõi artifact `kafka-streams`, Kafka client, state store và yêu cầu migration của Kafka Streams. Nâng Kafka Streams có thể liên quan đến state directory, changelog topic, repartition topic và cách khôi phục state.

Với serializer ngoài Apache Kafka, ví dụ JSON, Avro, Protobuf hoặc vendor serializer, cần ghi version riêng. Kiểm tra:

- Serializer/deserializer API có tương thích Kafka client không.
- Wire format và schema ID có tương thích dữ liệu cũ không.
- Schema Registry server version và client version.
- Compatibility mode của subject/schema.
- Reader/writer schema evolution.
- Topic chứa dữ liệu được tạo bởi phiên bản ứng dụng trước.

Một ứng dụng mới khởi động thành công không chứng minh có thể đọc mọi event đã tồn tại. Test dữ liệu fixture được tạo từ version cũ và version mới.

## 13. Xây dựng bảng compatibility matrix

Ma trận nên có một dòng cho mỗi tổ hợp môi trường và workload, thay vì chỉ ghi version mới nhất:

| Thành phần | Development | Staging | Production | Nguồn/ghi chú |
| --- | --- | --- | --- | --- |
| JDK | `<version>` | `<version>` | `<version>` | Vendor + support policy |
| Spring Boot | `<version>` | `<version>` | `<version>` | BOM/release notes |
| Spring Framework | `<resolved>` | `<resolved>` | `<resolved>` | Boot dependency management |
| Spring Kafka | `<resolved>` | `<resolved>` | `<resolved>` | Spring Kafka release notes |
| kafka-clients | `<resolved>` | `<resolved>` | `<resolved>` | Dependency tree + broker compatibility |
| Kafka broker | `<cluster version>` | `<cluster version>` | `<cluster version>` | Platform owner/upgrade plan |
| Kafka Streams | `<version hoặc N/A>` | `<version hoặc N/A>` | `<version hoặc N/A>` | Nếu workload dùng |
| Serializer/Registry | `<version>` | `<version>` | `<version>` | Wire format/schema policy |
| Test libraries | `<version>` | `<version>` | `<version>` | Cùng dòng runtime khi yêu cầu |

Bổ sung các cột `status`, `last verified`, `owner`, `evidence link`, `known limitation` và `next review date`. Giá trị có thể là `candidate`, `tested`, `approved`, `deprecated` hoặc `blocked`.

Không điền `tested` chỉ vì dependency resolve thành công. Trạng thái phải phản ánh bằng chứng kiểm thử của tổ hợp cụ thể.

## 14. Phân biệt compatibility matrix và upgrade target matrix

Hai bảng có mục đích khác nhau:

- **Compatibility matrix** ghi tổ hợp hiện đang chạy hoặc đã được xác minh.
- **Upgrade target matrix** ghi tổ hợp dự kiến nâng cấp, các bước chuyển tiếp và điều kiện chấp nhận.

Ví dụ:

| Hạng mục | Current | Target | Bằng chứng cần có |
| --- | --- | --- | --- |
| Spring Boot | `<current>` | `<target>` | Release notes, dependency BOM |
| Spring Kafka | `<current>` | `<target>` | API migration và integration tests |
| Kafka client | `<current>` | `<resolved target>` | Dependency tree và broker protocol |
| Broker | `<current>` | `<target>` | Kafka upgrade guide và mixed-version test |
| JDK | `<current>` | `<target>` | Framework support và runtime test |

Không ghi target vào cột current trước khi production rollout hoàn tất. Nếu môi trường staging đã nâng cấp còn production chưa, giữ hai trạng thái riêng.

## 15. Theo dõi deprecation và API migration

Release notes của Spring Kafka và Spring Boot cần được đọc trước khi nâng cấp. Một API có thể vẫn compile nhưng đã deprecated, hoặc behavior của handler/container đã đổi.

Các vùng API cần rà soát trong ứng dụng messaging:

- Error handling: legacy `ErrorHandler` và các API `CommonErrorHandler`/`DefaultErrorHandler`.
- Retry: blocking retry, retry topic và recovery configuration.
- Listener container: transaction manager, acknowledgment, pause/resume và concurrency.
- Producer: transaction, idempotence, callbacks và observation.
- Message conversion: JSON serializer/deserializer, trusted packages và type headers.
- Consumer: group protocol, isolation level và offset management.
- Test: `@EmbeddedKafka`, `KafkaTestUtils` và test lifecycle.

Danh sách này là vùng cần kiểm tra, không phải tuyên bố rằng mọi API đều bị loại bỏ trong cùng một release. Xác minh deprecation/removal ở release notes và compiler warning của đúng phiên bản.

## 16. Property và default behavior có thể thay đổi

Nâng version có thể làm thay đổi default value hoặc cách property được bind. Một ứng dụng không sửa YAML vẫn có thể có behavior khác.

Rà soát các nhóm cấu hình:

- `spring.kafka.bootstrap-servers`, producer và consumer properties.
- `max.poll.records`, `max.poll.interval.ms`, auto commit và isolation level.
- Retry/backoff, error handler và DLT destination.
- Transaction ID prefix và transaction timeout.
- Serializer/deserializer và message conversion.
- SSL/SASL properties, truststore và credential.
- Listener concurrency, AckMode và container lifecycle.
- Observation, metrics và tracing.

So sánh configuration metadata và release notes giữa source/target. Với property đã deprecated, lên kế hoạch chuyển trước khi bị remove. Không sao chép toàn bộ default cũ thành explicit config nếu chưa hiểu lý do; điều đó có thể ngăn ứng dụng nhận cải tiến mặc định ở bản mới.

## 17. Quy trình đánh giá một bản nâng cấp

Một bản nâng cấp có kiểm soát nên đi qua các bước:

1. Ghi lại current matrix và dependency tree.
2. Chọn target release còn được hỗ trợ theo chính sách tổ chức.
3. Đọc release notes của Boot, Spring Kafka, Kafka client và broker.
4. Xác định Java baseline và build tool/plugin requirements.
5. Tìm API deprecated/removed và property behavior changes.
6. Xác minh broker/client protocol và feature requirements.
7. Cập nhật BOM hoặc dependency constraints theo một nguồn quản lý rõ ràng.
8. Compile và chạy unit/component tests.
9. Chạy integration tests với broker version gần production.
10. Chạy contract test với event/schema cũ và mới.
11. Chạy performance/regression test cho throughput, latency và memory.
12. Triển khai staging/canary, quan sát metrics.
13. Rollout production theo kế hoạch và cập nhật matrix sau khi hoàn tất.

Nếu thay đổi đồng thời Boot, Spring Kafka, broker và JDK, sẽ khó xác định nguyên nhân khi lỗi. Khi có thể, chia thành các thay đổi nhỏ có thể xác minh độc lập.

## 18. Kiểm thử tương thích cần những lớp nào?

Một bộ kiểm thử phù hợp nên có:

| Test | Điều cần xác nhận |
| --- | --- |
| Compile/API | Mã nguồn và API dùng trong ứng dụng còn hợp lệ |
| Unit | Business logic, retry classifier và serializer wrapper |
| Spring context | Auto-configuration, bean wiring và listener startup |
| Embedded Kafka | Listener, producer, DLT và offset flow cơ bản |
| Testcontainers/broker thật | Broker/client protocol, transactions, group behavior |
| Schema compatibility | Đọc event cũ và ghi event mới |
| Security integration | TLS/SASL, principal và ACL |
| Performance regression | Throughput, latency, heap, GC và consumer lag |
| Rolling upgrade test | Mixed broker/client version và rebalance |
| Recovery test | Restart, retry, DLT, transaction rollback và replay |

`@SpringBootTest` thành công chỉ chứng minh context khởi tạo được. Nó không thay thế kiểm thử với broker thật, schema cũ hoặc lỗi mạng.

## 19. Test ma trận theo nhiều môi trường

Development, staging và production có thể dùng broker version hoặc security configuration khác nhau. Không được suy ra production tương thích chỉ từ local Embedded Kafka.

Ghi rõ các khác biệt:

- Broker version và topology.
- Replication factor, min ISR và topic configuration.
- TLS/SASL mechanism và ACL authorizer.
- Transaction coordinator configuration.
- Schema Registry version và compatibility mode.
- Network latency, DNS và quota.
- JDK/container image.
- Số partition, record size và traffic profile.

Staging nên gần production về protocol, security và topology nhất có thể. Nếu staging không thể giống hoàn toàn, ghi limitation và bổ sung test chuyên biệt cho phần khác biệt.

## 20. Theo dõi feature gate và giới hạn broker

Một số feature yêu cầu client và broker cùng hỗ trợ, đôi khi còn cần cấu hình broker hoặc topic. Ma trận nên có một bảng feature riêng:

| Feature | Client/API | Broker requirement | Config/test |
| --- | --- | --- | --- |
| Idempotent producer | Kafka client hỗ trợ | Broker hỗ trợ protocol cần thiết | Retry/restart và duplicate test |
| Kafka transactions | Spring Kafka + Kafka client | Transaction coordinator khả dụng | Commit/abort/read_committed test |
| Consumer group protocol mới | Kafka client hỗ trợ | Broker hỗ trợ protocol tương ứng | Rebalance/assignment test |
| Topic administration | AdminClient API | Broker hỗ trợ operation | ACL và timeout test |
| Kafka Streams feature | Kafka Streams/client | Broker và internal topic phù hợp | State restore/upgrade test |

Không đánh dấu feature là supported chỉ vì class hoặc property tồn tại. Kiểm tra broker minimum version, cluster setting, license/module nếu có và test runtime.

## 21. Nâng cấp broker và ứng dụng theo thứ tự

Nâng broker và nâng ứng dụng là hai thay đổi có thể phối hợp nhưng không phải lúc nào cũng phải làm cùng lúc. Thứ tự phụ thuộc Kafka release, client compatibility và feature được sử dụng.

Nguyên tắc:

- Đọc upgrade guide của Kafka source và target release.
- Kiểm tra rolling upgrade và mixed-version compatibility.
- Không nâng inter-broker protocol/version marker trước khi mọi broker đạt điều kiện theo hướng dẫn.
- Xác minh client cũ vẫn hoạt động trong giai đoạn broker đang mixed-version.
- Chỉ bật feature mới sau khi cluster và toàn bộ client cần thiết đã sẵn sàng.
- Nâng client ứng dụng theo canary để kiểm tra protocol và behavior.
- Theo dõi leader movement, ISR, request errors, consumer lag và transaction state.

Không tự suy ra thứ tự nâng broker từ số version lớn/nhỏ. Kafka có các bước migration riêng cho một số release; làm theo upgrade guide chính thức của phiên bản cụ thể.

## 22. Quản lý dependency override và exception

Đôi khi cần override `kafka-clients` hoặc một dependency vì security patch hoặc bug fix. Đây là ngoại lệ cần được ghi nhận, không nên trở thành cách quản lý version mặc định.

Một exception record nên có:

- Dependency và version do BOM quản lý.
- Version override.
- Lý do (CVE, bug, feature hoặc vendor requirement).
- Nguồn xác nhận tương thích với Spring Kafka.
- Test đã chạy và kết quả.
- Owner phê duyệt.
- Thời hạn xem xét lại và kế hoạch bỏ override.

Sau khi override, kiểm tra dependency tree và runtime package. Test classpath cũng cần tương thích; tránh runtime dùng Kafka client version khác với test chỉ vì dependency management khác scope.

## 23. Theo dõi security support và end of life

Tương thích kỹ thuật không đồng nghĩa còn được hỗ trợ bảo mật. Một tổ hợp có thể chạy được nhưng Spring Boot, Spring Kafka, Kafka broker hoặc JDK đã hết thời gian hỗ trợ theo chính sách vendor/community.

Ma trận nên ghi:

- Release đang dùng còn trong thời gian hỗ trợ hay không.
- Ngày kết thúc hỗ trợ nếu được công bố.
- Security advisory/CVE liên quan.
- Phiên bản vá tối thiểu.
- Owner chịu trách nhiệm nâng cấp.
- Deadline xử lý và trạng thái exception.

Không chỉ theo dõi version major. Patch release có thể chứa sửa lỗi bảo mật hoặc regression quan trọng. Theo dõi thông báo bảo mật của các dự án và vendor mà ứng dụng thực sự sử dụng.

## 24. Tự động hóa kiểm tra ma trận

Có thể tự động lấy version từ build và đưa vào báo cáo CI:

- Export Maven effective POM/dependency tree.
- Export Gradle runtime dependency report.
- Lấy JDK version từ build agent và container image.
- Lấy broker version từ platform inventory hoặc cluster admin.
- Đối chiếu với approved matrix.
- Fail build nếu dependency bị override ngoài policy.
- Đính kèm test result và commit SHA vào compatibility record.

Không nên scrape trang web tùy tiện để tự quyết định version được hỗ trợ. Tốt hơn là lưu approved constraints trong repository hoặc catalog có owner, rồi CI kiểm tra dependency thực tế so với catalog.

Ma trận cần review khi đổi Boot BOM, Spring Kafka, Kafka client, broker, JDK, serializer, Schema Registry hoặc security mechanism. Tạo lịch review định kỳ và review ngay khi có security advisory hoặc release support thay đổi.

## 25. Runbook khi phát hiện tổ hợp không tương thích

Khi ứng dụng lỗi sau nâng cấp:

1. Ghi lại chính xác version thực tế từ runtime và dependency tree.
2. So sánh với ma trận đã approved trước thay đổi.
3. Xác định lỗi xuất hiện ở compile, startup, TLS/authentication, protocol, listener hay data format.
4. Đọc release notes của từng thành phần thay đổi.
5. Kiểm tra `NoSuchMethodError`, `ClassNotFoundException`, `UnsupportedVersionException`, authentication/authorization error và serialization exception.
6. Tái hiện bằng broker/version và JDK tương ứng.
7. Thu hẹp thay đổi về một thành phần nếu có thể.
8. Chọn fix hoặc rollback theo kế hoạch đã kiểm chứng.
9. Chạy lại integration, schema và performance tests.
10. Cập nhật matrix, evidence và known limitation.

Không sửa bằng cách nâng tất cả dependency lên latest cùng lúc. Cách đó làm tăng số biến và khiến nguyên nhân khó xác định.

## 26. Rollback và giữ ma trận chính xác

Rollback ứng dụng có thể không đơn giản nếu broker hoặc schema đã được nâng cấp. Trước rollout, xác nhận target vẫn tương thích với broker hiện tại và bản ứng dụng cũ có thể chạy với cluster sau thay đổi.

Chuẩn bị:

- Artifact/container image của ứng dụng trước nâng cấp.
- Dependency lock hoặc BOM version cũ.
- Cấu hình cũ và secret reference.
- Khả năng tương thích client cũ với broker hiện tại.
- Schema backward/forward compatibility.
- Transactional ID và consumer group behavior khi rollback.
- Quy trình replay hoặc xử lý duplicate nếu offset/logic thay đổi.

Không rollback broker hoặc schema một cách tự động nếu đã có dữ liệu/metadata mới không tương thích với phiên bản cũ. Đánh dấu ma trận theo trạng thái thực tế sau rollback, không để target version vẫn hiển thị như current.

## 27. Mẫu hồ sơ xác minh một tổ hợp

Một record xác minh nên chứa:

| Trường | Nội dung |
| --- | --- |
| Workload | Service và consumer/producer group |
| Environment | Dev, staging hoặc production |
| JDK | Runtime/build version |
| Spring Boot | Version và BOM source |
| Spring Framework | Resolved version |
| Spring Kafka | Resolved version |
| kafka-clients | Runtime resolved version |
| Broker | Cluster version và topology |
| Serializer/Registry | Library và server version |
| Features | Transactions, retry, Streams, security... |
| Test evidence | Build, integration, schema, performance |
| Status | Candidate, tested, approved, deprecated hoặc blocked |
| Owner | Người/đội chịu trách nhiệm |
| Verified at | Ngày xác minh |
| Limitations | Giới hạn đã biết và điều kiện áp dụng |

Lưu evidence như dependency report, test report, release-note links và deployment revision. Không ghi secret, password, token hoặc private key vào compatibility matrix.

## 28. Checklist theo dõi ma trận phiên bản Spring Kafka

Trước khi phê duyệt một tổ hợp, xác nhận:

1. JDK build và runtime đáp ứng yêu cầu của Spring Boot target.
2. Spring Boot BOM quản lý đúng Spring Framework và Spring Kafka.
3. Spring Kafka và `kafka-clients` thực tế được resolve đã được kiểm tra.
4. `spring-kafka-test` tương thích với runtime dependency.
5. Kafka broker version và rolling-upgrade state được ghi nhận.
6. Client/broker protocol và feature requirements đã xác minh.
7. Kafka Streams/serializer/Schema Registry được kiểm tra nếu workload sử dụng.
8. API deprecated/removed và property default changes đã được rà soát.
9. Security support và end-of-life status còn phù hợp.
10. Unit, context, integration, schema và performance tests đạt.
11. Staging/canary đã xác minh với cấu hình gần production.
12. Rollback path tương thích với broker và schema sau thay đổi.
13. Dependency overrides có lý do, owner, evidence và review date.
14. Matrix có source link, last verified, owner và known limitations.
15. Current version chỉ cập nhật sau khi rollout thực tế hoàn tất.

Theo dõi ma trận phiên bản Spring Kafka là theo dõi một tổ hợp runtime đã được xác minh, không phải so sánh số version riêng lẻ. Bắt đầu từ Spring Boot BOM và dependency tree, sau đó kiểm tra JDK, Spring Kafka, Kafka client, broker, serializer và feature đang sử dụng. Ghi bằng chứng kiểm thử, giới hạn và owner cho từng môi trường; chỉ chuyển tổ hợp từ candidate sang approved khi build, integration, schema, security và vận hành đã được xác nhận.

