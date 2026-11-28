# Chọn phiên bản Java, Spring Boot, SDN, driver và Neo4j tương thích

Bài học này thuộc chương **Khởi tạo** của module **SPRING_DATA_NEO4J**. Module hướng dẫn xây dựng tầng dữ liệu đồ thị với Spring Data Neo4j (SDN) thông qua node entity, relationship, repository và truy vấn Cypher; đồng thời rèn cách mô hình hóa quan hệ, ánh xạ dữ liệu, quản lý transaction và tối ưu truy vấn trong ứng dụng Neo4j.

Để khởi tạo dự án ổn định, cần chọn đồng bộ Java, Spring Boot, Spring Data Neo4j, Neo4j Java Driver và Neo4j Server. Các thành phần này có chu kỳ phát hành và cách đánh số phiên bản riêng. Một phiên bản driver có thể kết nối được với một server nhưng chưa chắc toàn bộ tính năng mà SDN sinh ra đã tương thích với server đó. Cách an toàn là bắt đầu từ một dòng Spring Boot, dùng dependency management của dòng đó để chọn SDN và driver, sau đó đối chiếu server Neo4j với tài liệu tương thích của driver và SDN.

## 1. Vai trò của từng thành phần

| Thành phần | Vai trò | Điều cần kiểm tra |
|---|---|---|
| Java JDK | Biên dịch và chạy ứng dụng Spring Boot | Phiên bản tối thiểu của Spring Boot và Neo4j Java Driver |
| Spring Boot | Nền tảng ứng dụng, tự cấu hình các bean và quản lý dependency | Yêu cầu Java, Spring Framework và các phiên bản được quản lý |
| Spring Data Neo4j (SDN) | Ánh xạ node/relationship, cung cấp template và repository | Phiên bản Spring Data tương ứng với Spring Boot hoặc Spring Data BOM |
| Neo4j Java Driver | Kết nối ứng dụng với Neo4j qua giao thức Bolt, quản lý session và transaction | Phiên bản Java và các phiên bản server được hỗ trợ |
| Neo4j Server | Lưu trữ và thực thi truy vấn trên đồ thị | Phiên bản driver, phiên bản Cypher, yêu cầu JVM và chính sách hỗ trợ |

Có thể hình dung luồng phụ thuộc như sau:

```text
Java JDK
   |
   v
Spring Boot ---- quản lý phiên bản dependency
   |
   +---- Spring Data Neo4j
   |          |
   |          +---- Neo4j Java Driver
   |                         |
   +-------------------------+---- Bolt ----> Neo4j Server
```

SDN cung cấp mô hình lập trình ở tầng ứng dụng. Driver đảm nhiệm giao tiếp với database. Neo4j Server chạy độc lập, có thể nằm trên máy khác, trong container hoặc trên dịch vụ quản lý như Neo4j Aura. Vì vậy, JDK chạy ứng dụng và JVM chạy Neo4j Server là hai môi trường có thể được cấu hình riêng.

## 2. Chọn phiên bản Java trước khi tạo dự án

Java cần đáp ứng đồng thời yêu cầu của Spring Boot và Neo4j Java Driver. Nếu tự cài Neo4j Server trên cùng máy, cũng cần xem yêu cầu JVM của chính phiên bản server đó.

Tại thời điểm cập nhật bài học (26/11/2026), Spring Boot 4.2.0 yêu cầu tối thiểu Java 17 và hỗ trợ đến Java 27. Neo4j Java Driver thuộc dòng 6.x cũng yêu cầu Java 17 trở lên. Java 21 là lựa chọn LTS phù hợp cho ví dụ trong bài vì đáp ứng các yêu cầu này và cũng nằm trong dải JVM được Neo4j 5.26 hỗ trợ.

Khi chọn Java, cần phân biệt ba khái niệm:

- **JDK dùng để biên dịch:** phiên bản công cụ mà Maven hoặc Gradle sử dụng.
- **JRE/JVM chạy ứng dụng:** môi trường thực thi file JAR của Spring Boot. Thông thường nên dùng cùng major version với JDK build.
- **JVM chạy Neo4j Server:** môi trường của tiến trình database. Nếu database chạy trên máy hoặc container khác, JVM của server được cấu hình ở môi trường đó.

Ví dụ, ứng dụng có thể chạy bằng Java 21 và kết nối tới Neo4j Server 5.26 cũng chạy bằng Java 21. Nếu dùng Neo4j Aura, nhà cung cấp vận hành JVM của server; ứng dụng chỉ cần JDK phù hợp với Boot và driver.

Kiểm tra môi trường Java và Maven:

```bash
java -version
javac -version
mvn -version
```

Nếu `java` và `javac` trỏ tới hai JDK khác nhau, hoặc Maven dùng một JDK khác với IDE, dự án có thể biên dịch được ở một nơi nhưng không chạy được ở nơi khác. Hãy thống nhất `JAVA_HOME`, cấu hình IDE và toolchain của build tool.

## 3. Chọn dòng Spring Boot và Spring Data Neo4j

Spring Data Neo4j có số phiên bản riêng với Spring Boot. Không nên suy ra SDN 8.x sẽ đi với Boot 8.x, hoặc SDN 7.x sẽ đi với Boot 7.x. Spring Boot quản lý các phiên bản Spring Data tương thích thông qua dependency management. Khi dùng Spring Boot parent hoặc BOM, hãy để nó chọn phiên bản SDN tương ứng.

Hai tổ hợp tham khảo được quản lý bởi Spring Boot tại thời điểm viết bài:

| Dòng ứng dụng | Java tối thiểu | Spring Boot | Spring Data Neo4j được quản lý | Neo4j Java Driver được quản lý |
|---|---:|---:|---:|---:|
| Dự án mới theo dòng Boot hiện hành | 17 | 4.2.0 | 8.2.0 | 6.3.0 |
| Dự án đang duy trì trên Boot 3.5 | 17 | 3.5.16 | 7.5.13 | 5.28.13 |

Với dự án mới, có thể bắt đầu từ Spring Boot 4.2.0 và dùng Java 21. Spring Boot 4.2.0 được phát hành ngày 19/11/2026; dependency management của dòng này chọn Spring Data Neo4j 8.2.0 và Neo4j Java Driver 6.3.0. Nếu một hệ thống đang vận hành trên Spring Boot 3.5, nên giữ đồng bộ dòng 3.5 và các phiên bản do nó quản lý, trừ khi có kế hoạch nâng cấp major version đã được kiểm thử.

Không nên ghép tùy ý Spring Boot 4.x với SDN 7.x hoặc Spring Boot 3.5 với SDN 8.x. Các thế hệ này có thể phụ thuộc vào những thế hệ Spring Framework và Spring Data Commons khác nhau. Việc thay riêng một dependency có thể tạo ra lỗi liên kết lớp, lỗi khởi tạo bean hoặc hành vi không tương thích khi chạy.

### Spring Boot BOM giải quyết vấn đề gì?

BOM (Bill of Materials) là danh sách phiên bản dependency đã được phối hợp. Khi dùng Spring Boot parent hoặc import `spring-boot-dependencies`, ta khai báo dependency mà không phải tự điền phiên bản cho từng thư viện do Boot quản lý.

Ví dụ Maven với Spring Boot 4.2.0 và Java 21:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-neo4j</artifactId>
    </dependency>
</dependencies>
```

Không cần khai báo phiên bản riêng cho `spring-boot-starter-data-neo4j`, `spring-data-neo4j` hoặc `neo4j-java-driver` trong ví dụ này. Starter kéo theo SDN và driver với phiên bản đã được Boot quản lý. Cách này giảm nguy cơ chọn nhầm một tổ hợp dependency không tương thích.

Nếu không dùng Spring Boot, cần tự quản lý Spring Data BOM, Spring Framework, SDN và driver theo tài liệu của từng release train. Đây là cấu hình nâng cao; không nên sao chép phiên bản từ một dự án khác nếu chưa xác nhận chúng thuộc cùng thế hệ tương thích.

## 4. Chọn Neo4j Java Driver

Neo4j Java Driver là thư viện chính thức để ứng dụng Java giao tiếp với Neo4j qua Bolt. SDN sử dụng driver bên dưới để thực hiện thao tác đọc, ghi và transaction. Khi dùng starter của Spring Boot, driver được đưa vào thông qua dependency bắc cầu.

Tại thời điểm viết bài:

- Spring Boot 4.2.0 quản lý Neo4j Java Driver 6.3.0.
- Spring Boot 3.5.16 quản lý Neo4j Java Driver 5.28.13.
- Dòng driver 6.x yêu cầu Java 17 trở lên và hỗ trợ kết nối tới Neo4j 4.4.x, 5.x, 2025.x và 2026.x.

Thông tin tương thích của driver giúp xác định khả năng giao tiếp ở tầng Bolt. Nó không thay thế việc kiểm tra yêu cầu của SDN, Cypher-DSL, cú pháp Cypher hoặc tính năng database mà ứng dụng sử dụng.

Nếu ứng dụng chỉ dùng repository và `Neo4jTemplate`, hãy để starter quản lý driver. Chỉ khai báo trực tiếp `org.neo4j.driver:neo4j-java-driver` khi ứng dụng thật sự cần dùng API driver trực tiếp hoặc có lý do rõ ràng để tùy chỉnh. Khi override driver, phải kiểm tra phiên bản đó với SDN đang dùng và server đích; tránh để classpath có nhiều phiên bản driver ngoài ý muốn.

Một số hướng dẫn cũ đề cập Neo4j-OGM và các driver 4.x. Đó là cấu hình của những thế hệ SDN trước. Với Spring Data Neo4j hiện đại, hãy theo tài liệu đúng phiên bản SDN và không tự thêm Neo4j-OGM chỉ vì thấy nó trong một bài hướng dẫn cũ.

## 5. Chọn phiên bản Neo4j Server

Phiên bản server phải thỏa mãn cả khả năng kết nối của driver và các tính năng mà ứng dụng cần. Nếu môi trường production có yêu cầu hỗ trợ dài hạn, nên ưu tiên nhánh LTS còn được hỗ trợ và chọn bản vá mới nhất trong nhánh đó.

Một tổ hợp bảo thủ, phù hợp để học và phát triển ứng dụng tại thời điểm viết bài là:

| Thành phần | Phiên bản đề xuất | Lý do |
|---|---:|---|
| Java của ứng dụng | 21 | Đáp ứng yêu cầu của Spring Boot 4.2 và driver 6.x |
| Spring Boot | 4.2.0 | Dòng hiện hành, đã phát hành GA |
| Spring Data Neo4j | 8.2.0 | Phiên bản được Boot 4.2.0 quản lý |
| Neo4j Java Driver | 6.3.0 | Phiên bản được Boot 4.2.0 quản lý; thuộc dòng driver hỗ trợ Neo4j 5.x |
| Neo4j Server | 5.26.34 LTS | Nhánh LTS 5.26; driver 6.x hỗ trợ server 5.x |

Neo4j 5.26 hỗ trợ JVM Java 17 và Java 21. Do đó Java 21 là điểm giao thuận tiện giữa ứng dụng và server. Có thể sử dụng Neo4j 5.26.34 hoặc bản vá mới hơn trong nhánh 5.26 khi có phát hành và đã được kiểm tra trong môi trường dự án.

Driver 6.x cũng có thể kết nối với server Neo4j 2025.x và 2026.x. Tuy nhiên, khả năng kết nối của driver chưa chứng minh mọi truy vấn mà SDN sinh ra đều tương thích với phiên bản server mới hơn. Khi chọn nhánh 2025.x hoặc 2026.x, hãy kiểm tra tài liệu SDN/Cypher-DSL, phiên bản Cypher, các tính năng được dùng và chạy integration test trên đúng server mục tiêu. Không nâng cấp server production chỉ dựa trên việc driver chấp nhận phiên bản đó.

Đối với dự án hiện hữu đang dùng Boot 3.5.16, tổ hợp Boot 3.5.16 + SDN 7.5.13 + driver 5.28.13 + Neo4j 5.26.34 cũng là một hướng tham khảo. Driver 5.28.x hỗ trợ server Neo4j 5.x; vẫn cần kiểm tra bản vá cụ thể và kiểm thử truy vấn trước khi triển khai.

## 6. Hiểu cách đánh số phiên bản

Các dự án không dùng chung một quy tắc đánh số phiên bản:

| Dự án | Ví dụ | Cách đọc |
|---|---|---|
| Java | 21 | Major release của nền tảng Java; cần xem chính sách hỗ trợ của nhà phân phối JDK |
| Spring Boot | 4.2.0 | Major, minor và patch; thay đổi major có thể kéo theo thay đổi tương thích |
| Spring Data Neo4j | 8.2.0 | Phiên bản module Spring Data; được phối hợp qua release train |
| Neo4j Java Driver | 6.3.0 | Major driver; major line có yêu cầu Java và phạm vi server riêng |
| Neo4j Server | 5.26.34 hoặc 2026.10.2 | Neo4j 4/5 dùng SemVer; từ 2025 dùng CalVer theo năm.tháng.patch |

Neo4j Server chuyển sang Calendar Versioning từ bản 2025.01. Ví dụ `2026.10.2` nghĩa là nhánh phát hành tháng 10 năm 2026, bản vá thứ hai. Một hậu tố `LTS` trong số phiên bản đánh dấu nhánh hỗ trợ dài hạn. Neo4j 5.26 là nhánh LTS; nhánh 4.4 đã kết thúc hỗ trợ dài hạn vào ngày 30/11/2025.

Không so sánh số phiên bản giữa các dự án như thể chúng thuộc cùng một dòng. Ví dụ SDN 8.2.0 không phải phiên bản driver tương ứng 8.2.0; phiên bản driver tương thích được xác định bởi BOM và tài liệu của SDN/Boot.

## 7. Tạo dự án và xác minh dependency thực tế

Với Maven, sau khi thêm parent và starter như ví dụ ở trên, hãy kiểm tra các dependency mà Maven thực sự phân giải. Phiên bản ghi trong file POM không phải lúc nào cũng là phiên bản cuối cùng trên classpath, vì dependency management, dependency bắc cầu hoặc override có thể thay đổi kết quả.

```bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-neo4j,org.neo4j.driver:neo4j-java-driver
```

Trong tổ hợp Boot 4.2.0, kết quả cần cho thấy SDN 8.2.0 và driver 6.3.0, trừ khi dự án đã chủ động cấu hình override. Nếu kết quả có nhiều phiên bản hoặc một phiên bản khác ngoài dự kiến, hãy xem dependency nào đưa phiên bản đó vào và điều chỉnh dependency management.

Kiểm tra Java mà Maven sử dụng:

```bash
mvn -version
```

Kết quả cần cho thấy Maven đang chạy trên JDK phù hợp với cấu hình dự án. Trong CI, hãy cấu hình cùng Java toolchain hoặc image build với môi trường phát triển để tránh khác biệt giữa máy cá nhân và pipeline.

## 8. Kết nối tới Neo4j sau khi chọn phiên bản

Khi dùng `spring-boot-starter-data-neo4j`, Spring Boot tự cấu hình driver và hỗ trợ quét repository theo cấu hình mặc định. Chỉ cần khai báo URI và thông tin xác thực trong `application.properties`:

```properties
spring.neo4j.uri=bolt://localhost:7687
spring.neo4j.authentication.username=neo4j
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
```

Với môi trường Neo4j Aura hoặc endpoint yêu cầu TLS, sử dụng URI và cấu hình bảo mật do môi trường đó cung cấp, thường là URI dạng `neo4j+s://...`. Không lưu mật khẩu production trực tiếp trong mã nguồn hoặc file cấu hình được commit; nên truyền qua biến môi trường hoặc secret manager.

Sau khi cấu hình, cần kiểm tra kết nối thật tới đúng server đã chọn. Một ứng dụng biên dịch thành công chưa chứng minh database đang chạy, thông tin xác thực hợp lệ hoặc phiên bản server hỗ trợ toàn bộ truy vấn của ứng dụng. Hãy kiểm tra log khởi động, thực hiện một truy vấn đọc đơn giản và chạy integration test trên cùng phiên bản Neo4j mà môi trường triển khai sử dụng.

## 9. Các lỗi thường gặp khi chọn phiên bản

**Chỉ cập nhật phiên bản Spring Boot trong khi giữ dependency cũ.** Khi đổi major version, các dependency Spring Framework và Spring Data có thể thay đổi. Hãy kiểm tra lại BOM và các override sau mỗi lần nâng cấp.

**Gắn phiên bản thủ công cho mọi dependency.** Việc tự pin SDN và driver có thể ghi đè phiên bản mà Spring Boot đã kiểm tra cùng nhau. Hãy bỏ version riêng nếu không có yêu cầu đặc biệt.

**Nhầm Java của ứng dụng với Java của Neo4j Server.** Driver yêu cầu Java cho tiến trình ứng dụng; server có yêu cầu JVM riêng. Kiểm tra cả hai môi trường, nhất là khi chạy database trong container hoặc trên máy chủ từ xa.

**Dùng driver mới để kết luận server mới chắc chắn tương thích với SDN.** Driver xác nhận phạm vi giao tiếp Bolt. SDN còn phụ thuộc vào Cypher-DSL, cú pháp Cypher và khả năng của database. Hãy xác nhận cả tầng truy vấn.

**Dùng hướng dẫn Neo4j-OGM cũ cho SDN hiện đại.** Các thế hệ SDN cũ có cách tích hợp khác. Luôn kiểm tra tên artifact, annotation và cấu hình theo tài liệu đúng major version.

**Không kiểm tra dependency tree.** Một thư viện khác có thể kéo thêm phiên bản driver hoặc Spring Data. Xem dependency tree để xác định phiên bản thực sự được đóng gói.

## 10. Quy trình chọn phiên bản có thể lặp lại

1. Xác định phiên bản Java được tổ chức hỗ trợ và phiên bản JDK có trong môi trường build/runtime.
2. Chọn dòng Spring Boot phù hợp với yêu cầu ứng dụng và kiểm tra System Requirements.
3. Dùng Spring Boot parent/BOM để nhận phiên bản SDN và Neo4j Java Driver đã được quản lý.
4. Chọn Neo4j Server còn được hỗ trợ, ưu tiên LTS nếu cần vòng đời dài; kiểm tra driver hỗ trợ server đó.
5. Kiểm tra yêu cầu JVM của server và các tính năng Cypher mà SDN/ứng dụng sử dụng.
6. Xem effective POM hoặc dependency tree để xác nhận phiên bản thực tế.
7. Chạy integration test trên đúng phiên bản server dự kiến triển khai trước khi nâng cấp production.

Điểm cốt lõi là chọn theo **một bộ phiên bản đã được quản lý và kiểm chứng**. Với dự án mới trong ví dụ này, Java 21 + Spring Boot 4.2.0 + SDN 8.2.0 + driver 6.3.0 + Neo4j 5.26.34 LTS tạo thành một điểm bắt đầu rõ ràng. Khi nâng cấp bất kỳ thành phần nào, hãy kiểm tra lại ma trận tương thích và chạy kiểm thử tích hợp.

## Tài liệu tham khảo chính thức

- [Spring Boot 4.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.2 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Data Neo4j — Dependencies](https://docs.spring.io/spring-data/neo4j/reference/dependencies.html)
- [Spring Data Neo4j — Getting Started](https://docs.spring.io/spring-data/neo4j/reference/getting-started.html)
- [Neo4j Java Driver — Installation and Server Compatibility](https://neo4j.com/docs/java-manual/current/install/)
- [Neo4j Operations Manual — System Requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/)
- [Neo4j Upgrade and Migration Guide — Versioning and LTS](https://neo4j.com/docs/upgrade-migration-guide/current/)
