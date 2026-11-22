# Kiểm tra phiên bản đặc tả cùng mức hỗ trợ thực tế trong JPA

Trong kiến trúc ORM, câu hỏi “dự án đang dùng JPA phiên bản nào?” thường chưa đủ để quyết định một tính năng có hoạt động hay không. Một ứng dụng có thể khai báo **Jakarta Persistence API 3.1**, biên dịch được annotation và phương thức tương ứng, nhưng chạy với **persistence provider** cũ, bộ thư viện bị ghi đè phiên bản, một application server cung cấp implementation khác hoặc một database chưa hỗ trợ kiểu dữ liệu cần dùng.

Vì vậy cần kiểm tra **hai vấn đề tách biệt nhưng liên quan**:

1. **Phiên bản đặc tả (specification version):** hợp đồng chuẩn mà ứng dụng nhắm đến quy định những gì?
2. **Mức hỗ trợ thực tế (effective support):** toàn bộ stack đang chạy có triển khai đúng chức năng ấy với cấu hình và database đang sử dụng không?

Bài học hướng dẫn đọc và đối chiếu các phiên bản trong hệ sinh thái Java Persistence, kiểm tra dependency lúc build và runtime, tra cứu nguồn chứng cứ, rồi xác nhận bằng bài kiểm tra chạy thật.

## 1. Bản đồ các lớp phiên bản của ứng dụng JPA

JPA (Java Persistence API) là tên gọi quen thuộc ở các thế hệ Java EE; trong hệ sinh thái Jakarta EE, đặc tả mang tên **Jakarta Persistence**. Tên “JPA” vẫn thường được dùng để chỉ kiến trúc/API persistence theo mô hình này.

```text
                  MÃ NGUỒN ỨNG DỤNG
      Entity, JPQL, Criteria, EntityManager
                         |
                         v
              ĐẶC TẢ PERSISTENCE
           Quy tắc API và hành vi chuẩn
                         |
                         v
                   API ARTIFACT
      javax.persistence-api / jakarta.persistence-api
                         |
                         v
                 JPA IMPLEMENTATION
         Hibernate ORM / EclipseLink / ...
                         |
                         v
              FRAMEWORK / CONTAINER
    Spring, Jakarta EE server, Quarkus, cấu hình boot
                         |
                         v
                 JDBC + DIALECT
              Driver, ánh xạ SQL, DDL
                         |
                         v
                     DATABASE
               PostgreSQL, Oracle, ...
```

Đây là **các vai trò**, không nhất thiết là những thư viện độc lập hoàn toàn. Framework có thể quản lý phiên bản provider, còn provider có thể kéo API artifact qua dependency bắc cầu. Trong Jakarta EE server, container có thể cung cấp cả API lẫn implementation.

| Thành phần | Quyết định điều gì? | Dấu vết cần kiểm tra |
|---|---|---|
| **Đặc tả Jakarta Persistence** | Danh sách chức năng chuẩn, cách sử dụng API và hành vi phải tuân thủ | Tài liệu specification, API docs, release notes |
| **API artifact** | Lớp/annotation/method có sẵn khi biên dịch; package `javax.persistence` hoặc `jakarta.persistence` | Dependency và classpath/module path |
| **Persistence provider** | Cách triển khai `EntityManager`, JPQL, mapping, dirty checking, lazy loading… | Phiên bản Hibernate ORM/EclipseLink, tài liệu hỗ trợ spec |
| **Framework/container** | Cách khởi tạo `EntityManagerFactory`, quản lý transaction, chọn provider và dependency | BOM, dependency management, cấu hình, startup logs |
| **JDBC driver và SQL dialect** | Kết nối, truyền kiểu dữ liệu, sinh SQL tương thích | Phiên bản driver/dialect, log SQL, cấu hình datasource |
| **Hệ quản trị cơ sở dữ liệu** | Khả năng thực thi SQL, kiểu cột, khóa, transaction, constraint… | Version thực tế của database, tài liệu vendor, integration test |

**Nguyên tắc cốt lõi:** có lớp API trên classpath chỉ xác nhận rằng ứng dụng *nhìn thấy hợp đồng API*. Nó **không tự chứng minh** provider đang chạy triển khai đầy đủ hợp đồng đó.

## 2. “Phiên bản JPA” nghĩa là phiên bản nào?

### 2.1. Phân biệt Java EE JPA với Jakarta Persistence

Một số mốc giúp nhận diện nhánh API:

| Dòng đặc tả | Package persistence | Ghi chú kiến trúc |
|---|---|---|
| **JPA 2.2** (Java EE) | `javax.persistence.*` | Nhánh API trước khi chuyển namespace sang Jakarta |
| **Jakarta Persistence 3.0** | `jakarta.persistence.*` | Chuyển namespace từ `javax.persistence` sang `jakarta.persistence` |
| **Jakarta Persistence 3.1** | `jakarta.persistence.*` | Tiếp tục mở rộng API; ví dụ chuẩn hóa `GenerationType.UUID` |
| **Jakarta Persistence 3.2** | `jakarta.persistence.*` | Một phiên bản đặc tả sau 3.1; phải đối chiếu release notes để biết chức năng nào được thêm/sửa |

Đây là **các mốc ví dụ**, không phải tuyên bố phiên bản mới nhất tại mọi thời điểm. Trước khi nâng cấp hoặc chọn tính năng mới, kiểm tra danh mục đặc tả chính thức: [Jakarta Persistence Specifications](https://jakarta.ee/specifications/persistence/).

Việc đổi `javax.persistence` sang `jakarta.persistence` là thay đổi tên package ở mã nguồn, annotation, bytecode, descriptor và thư viện tích hợp. Không thể kết luận một provider dùng API cũ sẽ hiểu entity viết theo namespace mới chỉ vì đã thêm file JAR API mới.

Ví dụ hai đoạn khai báo thuộc **hai dòng API khác nhau**:

```java
// Dòng Java EE / JPA 2.2
import javax.persistence.Entity;
import javax.persistence.Id;
```

```java
// Dòng Jakarta Persistence 3.x
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
```

Tên annotation giống nhau nhưng hai lớp annotation có tên đầy đủ khác nhau. Đổi import không giải quyết được việc provider, framework và các thư viện mở rộng chưa tương thích.

### 2.2. API version khác implementation version

Hai tọa độ Maven có ý nghĩa khác nhau:

```text
jakarta.persistence:jakarta.persistence-api
    -> Bản API của đặc tả Jakarta Persistence

org.hibernate.orm:hibernate-core
    -> Một implementation (Hibernate ORM), có cách đánh số phiên bản riêng
```

Một dòng chữ “Hibernate ORM 6.x” **không đồng nghĩa** “Jakarta Persistence 6.x”. Số phiên bản provider không cần trùng số phiên bản đặc tả. Tương tự, tên phiên bản Spring Boot, Jakarta EE Platform, EclipseLink hoặc JDBC driver không phải số phiên bản Persistence API.

Một provider có thể hỗ trợ một đặc tả nhất định và đồng thời cung cấp **extension riêng** như annotation, kiểu custom, cú pháp truy vấn bổ sung. Chức năng chạy được trên provider đó vẫn có thể **không portable** sang provider khác.

### 2.3. Cấu hình yêu cầu khác với tính năng đã được xác nhận

Những bằng chứng sau mang ý nghĩa khác nhau:

```text
pom.xml/Gradle khai báo API 3.1
  -> Ý định dùng API 3.1, chưa chắc là bản được chọn cuối cùng.

persistence.xml version="3.1"
  -> Phiên bản descriptor được khai báo, chưa chứng minh provider hỗ trợ đủ 3.1.

Mã nguồn compile với GenerationType.UUID
  -> Compiler nhìn thấy enum constant này, chưa chứng minh DB hoạt động.

Startup log in ra phiên bản provider
  -> Cho biết provider thực tế, cần đối chiếu compatibility và cấu hình.

Integration test persist -> flush -> clear -> find thành công
  -> Chứng cứ chức năng đã chạy trong môi trường thử nghiệm cụ thể.
```

Mức tin cậy tăng khi kết hợp nhiều bằng chứng, nhưng **kết quả trên H2 không tự chứng minh ứng dụng tương thích hoàn toàn với Oracle hoặc PostgreSQL**.

## 3. Xác định yêu cầu tính năng trước khi tra phiên bản

Đừng chỉ hỏi “provider có hỗ trợ Jakarta Persistence 3.1 không?”; hãy chỉ rõ thao tác cần chạy.

Ví dụ một yêu cầu chức năng có thể là:

> Entity có khóa `UUID`; sử dụng `@GeneratedValue(strategy = GenerationType.UUID)`; lưu, đọc lại và truy vấn được trên PostgreSQL của môi trường triển khai.

Từ yêu cầu đó, cần giải đáp nhiều câu hỏi:

1. **Đặc tả:** tính năng này được quy định ở phiên bản Jakarta Persistence nào?
2. **API:** dependency đã được resolve có enum constant/annotation cần dùng không?
3. **Provider:** phiên bản provider hỗ trợ tính năng đó ở mức chuẩn hay extension?
4. **Runtime:** phiên bản thực tế được nạp có đúng như lúc build không?
5. **Database:** UUID được ánh xạ thành cột và giá trị SQL theo cách nào?
6. **Kiểm chứng:** persist, flush, clear, find và truy vấn có chạy trên database mục tiêu không?

Một ứng dụng khác chỉ dùng `@Entity`, `@Id` và JPQL đơn giản có thể không cần nâng cấp chỉ để lấy API mới. Phiên bản nên xuất phát từ **chức năng cần có, mức tương thích và chính sách hỗ trợ**, không chỉ từ mong muốn dùng số phiên bản cao nhất.

## 4. Kiểm tra phiên bản đã resolve trong hệ thống build

### 4.1. Vì sao không chỉ nhìn file `pom.xml` hoặc `build.gradle`?

Tệp khai báo có thể chứa:

- Phiên bản tường minh của dependency.
- Phiên bản do **BOM/platform** quản lý.
- Phiên bản do parent POM quản lý.
- Dependency bắc cầu kéo thêm API/provider khác.
- Cấu hình khác nhau cho `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`.
- Override từ dependency constraints, resolution rules hoặc application server.

Muốn biết “thực tế có gì”, cần xem **dependency graph đã được giải quyết** cho đúng module và classpath. Các lệnh bên dưới là thao tác người phát triển có thể chạy trong dự án; chúng không thay thế việc kiểm tra runtime của deployment.

### 4.2. Maven: đọc cây dependency hiệu lực

Nếu dùng Maven Wrapper ở Windows:

```powershell
.\mvnw.cmd dependency:tree
```

Lọc riêng API:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=jakarta.persistence:jakarta.persistence-api"
```

Kiểm tra thêm implementation, chẳng hạn Hibernate:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=org.hibernate.orm:hibernate-core"
```

Với dự án cũ, kiểm tra artifact ở namespace cũ:

```powershell
.\mvnw.cmd dependency:tree "-Dincludes=javax.persistence:javax.persistence-api"
```

Các dependency do BOM hoặc parent quản lý có thể được xem thông qua:

```powershell
.\mvnw.cmd help:effective-pom
```

Trên Linux/macOS dùng `./mvnw` tương ứng. Nếu dự án không có wrapper, dùng `mvn`. Với multi-module Maven, cần chạy ở module đóng gói ứng dụng hoặc chọn module tương ứng bằng `-pl` để kết quả đúng classpath cần kiểm tra.

Giả sử kết quả mang tính minh họa:

```text
+- jakarta.persistence:jakarta.persistence-api:jar:3.1.0:compile
\- org.hibernate.orm:hibernate-core:jar:<provider-version>:runtime
```

Ý nghĩa: dependency API 3.1.0 xuất hiện trong graph, còn phiên bản provider cần xem **giá trị cụ thể** mà Maven trả về. Phần `<provider-version>` là ký hiệu minh họa, không phải số phiên bản thực.

Không khẳng định tương thích chỉ từ hai dòng: phải kiểm tra bảng hỗ trợ của chính bản provider đó.

### 4.3. Gradle: kiểm tra runtimeClasspath và lý do chọn version

Nếu dùng Gradle Wrapper trên Windows:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Tìm dependency cụ thể và lý do phiên bản được chọn:

```powershell
.\gradlew.bat dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
```

```powershell
.\gradlew.bat dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
```

Kiểm tra cả API cũ nếu đang di chuyển từ JPA 2.2:

```powershell
.\gradlew.bat dependencyInsight --dependency javax.persistence-api --configuration runtimeClasspath
```

Trên Linux/macOS dùng `./gradlew`. Nếu module ứng dụng tên `app` trong multi-project Gradle, dạng lệnh có thể là:

```powershell
.\gradlew.bat :app:dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
```

Cần phân biệt:

| Classpath | Câu hỏi kiểm tra |
|---|---|
| `compileClasspath` | Mã nguồn nhìn thấy những API nào khi biên dịch? |
| `runtimeClasspath` | Ứng dụng chạy bằng những artifact nào trong cấu hình thông thường? |
| `testRuntimeClasspath` | Bài test dùng provider, driver và thư viện nào? |

Nếu test dùng provider khác runtime production, bài test đi qua có thể không xác nhận được tổ hợp triển khai thật.

### 4.4. Với Spring Boot hoặc framework quản lý phiên bản

Khi framework cung cấp BOM/dependency management, các bản Hibernate, Jakarta Persistence API, driver và thư viện tích hợp thường được chọn theo một **tập phiên bản đã kiểm thử cùng nhau**. Tự nâng một artifact lên riêng lẻ có thể phá tương thích giữa thư viện framework và provider.

Ví dụ:

```text
Ứng dụng Spring Boot
    -> dependency management chọn hibernate-core
    -> hibernate-core phụ thuộc các thư viện runtime
    -> API persistence được resolve theo graph cuối cùng
```

Quy trình an toàn là: xác định phiên bản framework đang dùng; xem tài liệu compatibility của release đó; đọc dependency graph cuối cùng; rồi chạy bài test tích hợp của ứng dụng. Không nên quyết định “Hibernate tương thích” chỉ vì khai báo tùy ý một số version trong build file.

Trong container Jakarta EE đầy đủ, nhiều dependency có thể được đánh dấu `provided` (Maven) hoặc `compileOnly` (Gradle). Khi đó **implementation thực tế đến từ server**, nên chỉ đọc dependency graph của ứng dụng sẽ bỏ sót thành phần quan trọng.

## 5. Kiểm tra provider và database đang thực sự chạy

### 5.1. Từ cấu hình tới bằng chứng runtime

Một số nơi thường cần xem:

- Startup logs có tên/phiên bản Hibernate ORM hoặc EclipseLink.
- Cấu hình provider được chọn trong `persistence.xml`, framework hoặc container.
- Tài liệu và cấu hình app server nếu provider do server cung cấp.
- Artifact tồn tại trong package triển khai: executable JAR, WAR, image container, thư mục module của server.
- Driver và database version lấy từ kết nối thực tế.

Ví dụ khai báo provider trong `persistence.xml`:

```xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopPU">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
    </persistence-unit>
</persistence>
```

Đây chỉ là một descriptor tối giản minh họa. Cách cấu hình datasource, transaction và quét entity còn tùy môi trường triển khai. Giá trị `version="3.1"` mô tả phiên bản persistence XML; **nó không nâng cấp Hibernate** và cũng không chứng minh runtime chạy đúng 3.1.

Nếu app server hoặc framework tự chọn provider, cấu hình có thể không khai báo `<provider>` một cách trực tiếp. Khi có nhiều provider, cần xác minh provider được bootstrap thật sự chứ không dựa vào việc một JAR nào đó có mặt.

### 5.2. Đọc phiên bản của Hibernate khi dự án dùng Hibernate

Có thể dùng API riêng của Hibernate trong mã chẩn đoán:

```java
String providerVersion = org.hibernate.Version.getVersionString();
System.out.println("Hibernate ORM runtime: " + providerVersion);
```

Cách này **phụ thuộc Hibernate**, không phải API portable của Jakarta Persistence. Khi dùng EclipseLink hoặc provider khác, xem log hoặc cơ chế chẩn đoán được chính provider đó cung cấp.

Lưu ý:

- Tên class thực của `EntityManagerFactory` có thể là proxy do framework tạo; nó không phải bằng chứng tin cậy duy nhất về version.
- `EntityManagerFactory.getProperties()` cung cấp thuộc tính cấu hình nhưng Jakarta Persistence không bảo đảm một khóa chuẩn chứa “specification version đang được implementation hỗ trợ”.
- `Package.getImplementationVersion()` có thể trả `null` khi manifest không có metadata; đừng coi đó là nguồn sự thật duy nhất.
- Log “đã khởi động thành công” chứng minh boot được ở môi trường đó, chưa chứng minh toàn bộ tính năng mapping/truy vấn.

### 5.3. Lấy thông tin driver và database qua JDBC

Khi ứng dụng có `DataSource`, dùng metadata từ kết nối **thực tế**:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DatabaseVersionProbe {
    public static void printVersions(DataSource dataSource)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("Database: "
                + meta.getDatabaseProductName());
            System.out.println("Database version: "
                + meta.getDatabaseProductVersion());
            System.out.println("JDBC driver: "
                + meta.getDriverName());
            System.out.println("JDBC driver version: "
                + meta.getDriverVersion());
        }
    }
}
```

`javax.sql.DataSource` và `java.sql.*` là các API Java SE/JDBC. **Không đổi `javax.sql.DataSource` thành `jakarta.sql.DataSource`** khi di chuyển JPA sang Jakarta: package JDBC này không thuộc nhóm namespace đã chuyển.

Thông tin metadata cần được ghi vào bằng chứng môi trường (development, CI, staging, production). Cùng một binary ứng dụng có thể gặp kết quả khác nếu chạy trên database version khác, driver khác hoặc server cấu hình khác.

### 5.4. Với ứng dụng đóng gói và application server

Cần kiểm tra dependency không chỉ trong source mà còn **trong artifact triển khai**:

```text
Source / build dependency
       |
       v
Package: executable JAR / WAR / OCI image
       |
       v
Container class loader + server modules
       |
       v
Provider thực tế được bootstrap
```

Ví dụ một WAR có API `jakarta.persistence` nhưng lại được triển khai trên container chỉ cung cấp các thư viện kiểu `javax.persistence`; khi đó việc source compile không giúp runtime nhận diện entity.

Trong hệ thống nhiều class loader, xung đột có thể sinh ra do một module đóng gói provider khác bản do server cấp. Cần xem quy tắc class loading và cách server cung cấp Jakarta EE API, tránh chép các JAR tùy ý vào thư mục triển khai mà không hiểu tính tương thích.

## 6. Xác định một tính năng được “hỗ trợ” đến mức nào

“Hỗ trợ” có nhiều tầng. Nên lưu lại mức bằng chứng:

| Mức | Bằng chứng | Điều đã biết | Điều chưa được bảo đảm |
|---|---|---|---|
| **A — Có trong đặc tả** | Specification ghi chức năng đó | Chức năng thuộc hợp đồng chuẩn ở version cụ thể | Project đã dùng version ấy |
| **B — Có trong API** | Source compile được với artifact đã resolve | Kiểu/annotation/method tồn tại lúc compile | Implementation hiểu và chạy đúng |
| **C — Provider công bố hỗ trợ** | Compatibility matrix, release notes, issue chính thức hoặc chứng nhận phù hợp | Nhà cung cấp công bố phạm vi hỗ trợ | Môi trường database cụ thể đã được kiểm chứng |
| **D — Runtime xác định đúng stack** | Dependency graph, build artifact, startup log và JDBC metadata | Biết phiên bản thành phần được nạp | Tính năng chạy trong use case đang xét |
| **E — Tích hợp chạy thật** | Test trên provider, driver, database và cấu hình mục tiêu | Chức năng được xác nhận trong điều kiện test | Mọi cấu hình/mọi use case trong tương lai |

**TCK (Technology Compatibility Kit)** là bộ kiểm tra tuân thủ một đặc tả. Nếu một sản phẩm hoặc bản phát hành có kết quả/chứng nhận tương thích chính thức, đây là bằng chứng hữu ích về mức tuân thủ. Tuy nhiên, nó không có nghĩa mọi SQL extension, mọi database version, tính năng vendor hoặc cấu hình ứng dụng đều đã được kiểm tra.

Nguồn tài liệu nên đối chiếu, ưu tiên thông tin gắn với **đúng phiên bản**:

1. Trang Jakarta Persistence chính thức để xác định đặc tả và release notes: <https://jakarta.ee/specifications/persistence/>.
2. Tài liệu API/specification của chính version được chọn.
3. Tài liệu compatibility, migration và user guide của implementation đang dùng, ví dụ <https://hibernate.org/orm/documentation/> hoặc <https://eclipse.dev/eclipselink/>.
4. Tài liệu dependency management của framework/container đúng release.
5. Tài liệu JDBC driver và DBMS đúng version.
6. Integration test và log từ môi trường thực của dự án.

Không nên chỉ dựa vào một bài viết diễn đàn hay ví dụ sử dụng phiên bản khác. Một tính năng có thể **chạy nhờ extension** ở một provider nhưng không được định nghĩa tương ứng trong đặc tả mà ứng dụng nhắm đến.

## 7. Ví dụ kiểm tra hoàn chỉnh: sinh khóa UUID theo chuẩn

### 7.1. Yêu cầu và các điểm kiểm tra

Giả sử muốn dùng `GenerationType.UUID`, một chiến lược sinh khóa được Jakarta Persistence 3.1 đưa vào đặc tả.

Các điều kiện cần xác nhận:

- API được resolve có `jakarta.persistence.GenerationType.UUID`.
- Phiên bản provider công bố hỗ trợ cách sinh khóa này.
- Provider đang chạy thật đúng bản mong đợi.
- Mapping kiểu `java.util.UUID` được database mục tiêu xử lý đúng.
- Lệnh `persist`, `flush`, đọc lại bằng khóa và rollback/commit hoạt động như mong muốn.

### 7.2. Entity minh họa

```java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "version_probe")
public class VersionProbe {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false)
    private String label;

    protected VersionProbe() {
        // JPA tạo đối tượng qua constructor không tham số.
    }

    public VersionProbe(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label must not be blank");
        }
        this.label = label;
    }

    public UUID getId() {
        return id;
    }

    public String getLabel() {
        return label;
    }
}
```

Việc khai báo được `GenerationType.UUID` chỉ xác nhận **API đủ mới để compile**. Không nên kết luận provider đã hỗ trợ từ bước này.

### 7.3. Test đường đi persistence

Ví dụ sau nhận một `EntityManagerFactory` đã được cấu hình trỏ đến database kiểm thử. Nó dùng transaction kiểu `RESOURCE_LOCAL`; nếu ứng dụng dùng container-managed JTA transaction, cần chạy cùng ý tưởng test trong transaction do container/framework quản lý thay vì tự gọi `getTransaction()`.

```java
package com.example.persistence;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.UUID;

public final class VersionProbeCheck {

    public static void verify(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();
        try {
            em.getTransaction().begin();

            VersionProbe created = new VersionProbe("JPA check");
            em.persist(created);
            em.flush();

            UUID generatedId = created.getId();
            if (generatedId == null) {
                throw new AssertionError("UUID was not generated");
            }

            em.clear(); // Buộc thao tác find đọc lại từ persistence context trống.
            VersionProbe loaded = em.find(
                VersionProbe.class, generatedId
            );

            if (loaded == null
                    || !"JPA check".equals(loaded.getLabel())) {
                throw new AssertionError(
                    "Persist / reload did not work"
                );
            }

            em.getTransaction().rollback(); // Không để lại dữ liệu test.
        } catch (RuntimeException | Error failure) {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
            throw failure;
        } finally {
            em.close();
        }
    }
}
```

Test thực hiện đường đi `persist -> flush -> clear -> find`; do đã `clear`, `find` phải lấy lại trạng thái từ persistence, tránh việc chỉ đọc instance đang nằm sẵn trong first-level cache. Test này còn dựa vào schema/table `version_probe` đã tồn tại hoặc được tạo theo cơ chế test. Trên DB cụ thể, cần kiểm tra kiểu cột UUID được sinh và truy vấn SQL thực tế.

Để kiểm tra đầy đủ hơn ở CI, thêm tình huống commit transaction, mở transaction mới rồi tìm lại entity. Điều đó xác nhận đường đi **dữ liệu đã commit**, chứ không chỉ khả năng flush và đọc lại trong cùng một transaction.

### 7.4. Vì sao phải kiểm tra trên database mục tiêu?

Các database có cách biểu diễn UUID khác nhau: có hệ quản trị dùng kiểu `UUID` chuyên biệt, có hệ ánh xạ thông qua `BINARY`, `RAW` hoặc chuỗi. Phương án ánh xạ phụ thuộc cả provider, dialect và driver. Nếu thử nghiệm trên H2 nhưng triển khai trên Oracle/PostgreSQL, một số lỗi kiểu cột và SQL chỉ xuất hiện khi chạy môi trường mục tiêu.

Có thể tổ chức kiểm thử:

```text
Compile & unit test
       |
       v
Integration test với provider + DB test
       |
       v
Integration test với DB engine/version như production
       |
       v
Staging: đóng gói/runtime/configuration thực tế
       |
       v
Triển khai
```

**Chức năng “được hỗ trợ thực tế” là một kết luận có phạm vi:** hỗ trợ *chức năng X, trên provider Y, với database Z, trong cấu hình C, được chứng minh bằng test T*. Đây là phát biểu hữu ích hơn “ứng dụng dùng JPA mới”.

## 8. Một số tính năng cần đối chiếu riêng với provider

Không phải mọi tính năng có độ phụ thuộc runtime giống nhau.

| Nhóm chức năng | Cần đối chiếu điều gì? | Kiểm chứng nên có |
|---|---|---|
| **Sinh khóa**: `IDENTITY`, `SEQUENCE`, `UUID` | Phiên bản API/provider, kiểu cột và chiến lược DB | Insert, ID sau persist/flush, đọc lại |
| **Quan hệ và fetch** | Mapping, lazy proxy/bytecode enhancement, transaction | Số truy vấn, kết quả ngoài/sau transaction |
| **JPQL và Criteria** | Cú pháp chuẩn theo spec, function của provider, dialect | Chạy query với dữ liệu thật và so sánh kết quả |
| **AttributeConverter** | Hỗ trợ type conversion và kiểu JDBC tương ứng | Persist/reload giá trị, dữ liệu NULL, query |
| **Embedded/ElementCollection** | Cách ánh xạ thành cột hoặc bảng phụ | Insert/update/delete collection, ràng buộc |
| **Locking/transaction** | DB isolation, provider, transaction manager | Kiểm thử concurrent update và rollback |
| **Schema generation** | Thuộc tính chuẩn hay thuộc tính riêng provider; DDL DB cụ thể | Tạo schema trong DB test, kiểm tra constraint |
| **Cache và batch** | Provider extension, version, cấu hình | SQL count và test tính nhất quán; không chỉ nhìn cấu hình |
| **JSON, array hoặc kiểu DB đặc biệt** | Nhiều trường hợp là extension, không phải portable JPA | Mapping với driver/dialect của DB đích |

Một ví dụ điển hình: `FetchType.LAZY` có thể là **gợi ý** cho cách tải quan hệ tùy mapping và provider. Annotation compile được không đảm bảo lịch SQL tải thực tế giống suy đoán. Muốn xác nhận N+1 hoặc hiệu quả `fetch join`, cần bật SQL logging/metrics và thực hiện use case tương ứng.

Một ví dụ khác: JPQL sử dụng function của database thông qua `FUNCTION` có thể chạy trên một dialect, nhưng không nhất thiết khả chuyển sang database khác. Phải phân biệt chức năng **chuẩn của API** với **hành vi riêng provider hoặc SQL vendor**.

## 9. Di chuyển từ `javax.persistence` sang `jakarta.persistence`

Đây là một trong những bài toán phiên bản thường gặp nhất khi đổi kiến trúc JPA.

### 9.1. Vì sao đổi API dependency chưa đủ?

Giả sử một dự án cũ có:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.ManyToOne;
```

Sau khi đổi sang:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
```

Compiler cần `jakarta.persistence-api`, nhưng provider và framework cũng phải nhận diện đúng metadata Jakarta. Các annotation `javax.persistence.Entity` và `jakarta.persistence.Entity` là hai kiểu khác nhau ở runtime. Một phần dự án hoặc thư viện còn dùng namespace cũ có thể dẫn đến lỗi “not a managed type”, class không được quét hoặc xung đột API.

### 9.2. Cần đồng bộ những gì?

| Khu vực | Việc xem xét khi chuyển sang Jakarta |
|---|---|
| **Entity/source** | Import `jakarta.persistence.*`; chú ý `AttributeConverter`, listener, repository và base class |
| **Provider** | Chọn bản Hibernate/EclipseLink thực sự hỗ trợ dòng Jakarta đang dùng |
| **Framework** | Dùng release hỗ trợ Jakarta và tuân theo dependency management của release đó |
| **Descriptor** | Cập nhật `persistence.xml` và namespace/schema phù hợp |
| **Các API Jakarta EE liên quan** | Kiểm tra riêng Validation, Transactions, Servlet… nếu ứng dụng có sử dụng |
| **Thư viện thứ ba** | Đảm bảo thư viện tích hợp JPA nhận đúng namespace mới |
| **Bản đóng gói/server** | Tránh trộn API/provider cũ vào WAR/JAR/container mới |
| **Kiểm thử** | Bootstrap persistence context, persist/query, transaction và migration schema |

**Không thay tất cả từ khóa `javax.*` bằng `jakarta.*` một cách máy móc**. Nhiều package Java SE như `javax.sql.DataSource`, `javax.crypto` và `javax.naming` vẫn mang tên `javax`.

### 9.3. Chiến lược nâng cấp an toàn

1. Chụp lại stack đang chạy: Java runtime, framework, API, provider, driver, DB.
2. Chọn release framework/container có công bố hỗ trợ dòng Jakarta mục tiêu.
3. Kiểm tra release notes/migration guide và dependency graph, đặc biệt thư viện bên thứ ba.
4. Đổi source/descriptor và cấu hình triển khai đúng namespace.
5. Chạy tập integration test cốt lõi với provider và database mục tiêu.
6. Quan sát log boot, SQL, lỗi class loading và luồng transaction.
7. Chỉ kết luận hoàn tất khi bản đóng gói triển khai cũng vượt qua kiểm tra.

Nếu thư viện phụ thuộc chỉ hỗ trợ `javax.persistence`, không nên “vá” bằng cách thêm song song hai API như một giải pháp mặc định. Khi cần tạm tương thích, phải có chiến lược migration cụ thể và kiểm chứng các class được provider quản lý.

## 10. Chẩn đoán lỗi theo tầng phiên bản

| Triệu chứng | Nghi ngờ trước tiên | Hướng kiểm tra |
|---|---|---|
| `ClassNotFoundException` hoặc `NoClassDefFoundError` với `javax.persistence.*`/`jakarta.persistence.*` | Thiếu API runtime hoặc nhầm namespace | Resolved dependency, package triển khai, class loader |
| `NoSuchMethodError` ở API persistence | Biên dịch với một version, runtime nạp version khác | So sánh compile/runtime, BOM, server modules |
| “No Persistence provider for EntityManager…” | Provider không được phát hiện/cấu hình hoặc boot lỗi | JAR provider, `persistence.xml`, provider property, logs |
| “Not a managed type” / “Unknown entity” | Entity không được quét, annotation sai namespace hoặc mapping lỗi | Package scan, `@Entity`, provider, descriptor |
| Enum constant/annotation mới không compile | API được resolve chưa có chức năng | Phiên bản đặc tả, dependencyInsight/tree |
| Compile được nhưng provider báo không hỗ trợ | Implementation chưa triển khai hoặc tính năng cần cấu hình | Release notes provider đúng version, test thu hẹp |
| DB báo kiểu cột không hợp lệ hoặc SQL syntax error | Dialect/driver/DB khác nhau hoặc mapping không phù hợp | SQL thực tế, JDBC metadata, DDL và DB version |
| Test H2 qua nhưng production lỗi | Chênh lệch SQL dialect, schema, driver hoặc DB engine | Test với DB engine/version sản xuất |
| Sau `flush` vẫn không thấy thay đổi từ session khác | Transaction chưa commit hoặc isolation | Transaction boundary, rollback, isolation |
| Lazy loading lỗi ngoài transaction | Context đã đóng, fetch strategy chưa phù hợp | Thiết kế truy vấn, DTO projection, transaction scope |

**Quy trình khoanh vùng:**

```text
Lỗi compile?
   -> API / source / namespace / JDK

Lỗi ngay khi boot?
   -> Provider / framework / packaging / class loader

Lỗi khi persist hoặc truy vấn?
   -> Mapping / tính năng provider / dialect / schema

Lỗi chỉ trên một môi trường?
   -> DB, driver, transaction, config, runtime artifact

Lỗi khi nâng version?
   -> Đối chiếu release notes + thay đổi dependency graph
```

Một lỗi trong tầng dưới có thể xuất hiện dưới exception chung của tầng JPA. Vì vậy khi điều tra cần giữ cả **root cause** và các dòng SQL/log liên quan, không chỉ dòng thông báo ở controller.

## 11. Lập bảng tương thích có bằng chứng thay vì dựa vào phỏng đoán

Trong dự án nhóm, ghi lại một bản *compatibility record* cho từng lần nâng cấp hoặc thêm tính năng:

| Trường cần ghi | Ví dụ cách điền |
|---|---|
| Chức năng | `@GeneratedValue(strategy = GenerationType.UUID)` |
| Đặc tả yêu cầu | Jakarta Persistence 3.1 cho ví dụ này |
| API đã resolve | Tọa độ + version lấy từ Maven/Gradle |
| Provider đã resolve | Tên, version, tài liệu compatibility |
| Provider runtime | Phiên bản từ startup log hoặc chẩn đoán vendor |
| Framework/container | Tên + version + nguồn quản lý dependency |
| Java runtime | Vendor và version JDK chạy thật |
| Driver/DB | JDBC driver và DB product/version từ metadata |
| Kết quả test | Test name, CI run/commit, thành công/thất bại |
| Phạm vi kết luận | Dev/CI/staging/production, tính năng đã thử |
| Ngoại lệ đã biết | Chênh lệch dialect, behavior provider, hạn chế DB |

Có thể đánh dấu trạng thái cho **từng chức năng**:

- `PLANNED`: đang dự định dùng, chưa xem tài liệu.
- `SPEC_CONFIRMED`: biết chức năng thuộc phiên bản đặc tả nào.
- `PROVIDER_DOCUMENTED`: có tài liệu xác nhận provider/version.
- `INTEGRATION_VERIFIED`: đã chạy test trên cấu hình mục tiêu.
- `BLOCKED`: có xung đột hoặc thiếu hỗ trợ; ghi nguyên nhân.

Các trạng thái trên chỉ là quy ước quản lý kỹ thuật của nhóm, **không phải trạng thái chuẩn trong JPA**.

Ví dụ hồ sơ mang tính minh họa:

```yaml
feature: uuid-generated-id
specification: "Jakarta Persistence 3.1"
apiArtifact: "jakarta.persistence:jakarta.persistence-api"
apiVersion: "<resolved-version>"
provider: "Hibernate ORM"
providerVersion: "<observed-runtime-version>"
frameworkVersion: "<observed-runtime-version>"
database: "<product-and-version>"
jdbcDriver: "<driver-and-version>"
integrationTest: "VersionProbeCheck"
testResult: "<pass-or-fail>"
verifiedEnvironment: "<CI-or-staging-target>"
evidence:
  - "<link-to-provider-release-notes>"
  - "<link-to-CI-test-run>"
```

**Không điền số giả định** vào record như thể đã xác minh. Các placeholder chỉ được thay sau khi xem kết quả thực tế. Bảng này giúp người sau hiểu vì sao một version được chọn và khi nào cần chạy lại kiểm tra.

## 12. Tình huống thực hành

### Tình huống A: compile được, chạy báo `NoSuchMethodError`

Một lập trình viên thêm API artifact mới để sử dụng method mới; CI compile qua nhưng ứng dụng triển khai lỗi `NoSuchMethodError`.

Cách xử lý: xác định method/class báo lỗi, đọc dependency version ở compile và runtime, mở package triển khai để xem artifact thật, kiểm tra server có cấp thư viện khác hay không. Sau đó căn chỉnh BOM/provider/container và chạy lại integration test. **Không mặc định** đây là lỗi logic của entity.

### Tình huống B: Hibernate có tính năng nhưng JPQL không portable

Một dự án dùng HQL extension được Hibernate hỗ trợ. Khi chuyển provider, truy vấn không còn chạy.

Cần xác định tính năng đó thuộc JPQL chuẩn theo version đặc tả hay HQL/provider extension. Nếu cần khả chuyển, thay bằng JPQL/Criteria chuẩn hoặc đưa logic vào layer riêng với test cho từng provider. Nếu chủ đích phụ thuộc Hibernate, ghi rõ dependency công nghệ và phiên bản trong compatibility record.

### Tình huống C: ứng dụng Jakarta chạy trên server cũ

Ứng dụng dùng `jakarta.persistence.Entity` nhưng server được cấu hình chủ yếu cho stack Java EE/`javax.persistence`. Dù source compile, server không quét entity đúng hoặc thất bại ở bootstrap.

Cần xác định version Jakarta EE của server, version provider server cung cấp, khả năng triển khai ứng dụng Jakarta và quy tắc class loader. Nâng toàn stack tương thích hoặc chọn môi trường triển khai phù hợp, thay vì chỉ thêm một API JAR.

### Tình huống D: test xanh trên H2 nhưng lỗi kiểu UUID trên DB thật

Test persist/reload UUID hoạt động với H2, nhưng khi chạy DB mục tiêu provider sinh kiểu cột hoặc câu SQL không hợp lệ.

Kiểm tra metadata DB/driver, dialect provider, migration DDL và cách ánh xạ UUID. Thêm test integration với database mục tiêu (có thể qua container dùng đúng engine/version). Kết luận phải ghi phạm vi test, không gộp tất cả database thành một.

## 13. Câu hỏi tự luyện

**1.** Dự án khai báo `jakarta.persistence-api:3.1.0`. Có thể chắc chắn mọi chức năng Jakarta Persistence 3.1 chạy trên production không?

**Đáp án:** Không. Cần provider hỗ trợ, framework/container tương thích, runtime dùng đúng artifact và database phù hợp. Phải kiểm tra chức năng cụ thể.

**2.** Tại sao xem mỗi `pom.xml` chưa đủ để xác định phiên bản thực tế?

**Đáp án:** Dependency có thể chịu quản lý bởi BOM/parent, bị conflict resolution hoặc khác nhau theo scope và môi trường đóng gói. Phải xem graph đã resolve và runtime.

**3.** Ứng dụng dùng Hibernate 6.x thì đặc tả JPA cũng là 6.x?

**Đáp án:** Không. Số phiên bản Hibernate là phiên bản implementation; Jakarta Persistence dùng hệ đánh số riêng.

**4.** `persistence.xml version="3.1"` chứng minh điều gì?

**Đáp án:** Descriptor khai báo metadata theo phiên bản tương ứng; tự nó không chứng minh provider hay database hỗ trợ tính năng 3.1.

**5.** Vì sao `javax.sql.DataSource` vẫn hợp lệ trong ứng dụng Jakarta Persistence 3.x?

**Đáp án:** Đây là API JDBC thuộc Java SE, không phải `javax.persistence` đã chuyển namespace.

**6.** Một test dùng H2 pass có đủ chứng minh tính năng chạy trên Oracle phiên bản đang dùng trong production không?

**Đáp án:** Không. Phải kiểm tra dialect, driver, kiểu cột, SQL và transaction trên đúng DB engine/version mục tiêu.

**7.** Làm sao phân biệt “tính năng chuẩn Jakarta Persistence” với “Hibernate extension”?

**Đáp án:** Tra specification/API docs của version mục tiêu rồi đối chiếu tài liệu provider. Nếu chỉ có ở Hibernate, cần ghi rõ phụ thuộc implementation và kiểm tra portability.

**8.** Hai môi trường chạy cùng file JAR ứng dụng nhưng cho kết quả khác nhau. Cần nhìn vào đâu?

**Đáp án:** Kiểm tra container, classpath thực, provider, driver, DB version, schema, dialect, transaction manager và cấu hình môi trường; so sánh log, metadata và kết quả integration test.

## 14. Quy trình áp dụng khi bổ sung một tính năng JPA

Một nhóm triển khai có thể dùng quy trình sau cho mỗi tính năng hoặc lần nâng cấp:

1. **Mô tả hành vi muốn có** bằng use case cụ thể, tránh chỉ ghi “nâng JPA”.
2. **Xác nhận phiên bản đặc tả** định nghĩa chức năng và xem ghi chú thay đổi ở phiên bản đó.
3. **Xem API đã resolve** ở compile/runtime bằng công cụ build, kể cả dependency bắc cầu và BOM.
4. **Xác định provider thật** qua tài liệu compatibility và startup log/runtime artifact.
5. **Đối chiếu framework/container**, JDK, JDBC driver, dialect và database version.
6. **Xây test tích hợp tối thiểu** đi qua thao tác thật: persist, flush, clear, query, transaction và những trường hợp lỗi liên quan.
7. **Chạy trên DB/config mục tiêu**, không suy rộng kết quả từ DB giả lập.
8. **Lưu bằng chứng**: phiên bản quan sát được, log, tài liệu và kết quả CI.
9. **Chỉ kết luận trong phạm vi đã xác minh**; đánh dấu rõ điểm nào mới ở mức tài liệu hoặc chưa kiểm tra.

Với cách làm này, nhóm có thể diễn đạt kết quả chính xác: “Chức năng X thuộc đặc tả Jakarta Persistence phiên bản Y, được provider Z phiên bản W công bố hỗ trợ và đã qua bài test T trên database D phiên bản V”. Đó mới là căn cứ có giá trị khi quyết định sử dụng API, nâng cấp ORM hoặc triển khai ứng dụng JPA.

### Tài liệu tham khảo chính thức

- [Jakarta Persistence — danh mục phiên bản đặc tả](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence 3.1](https://jakarta.ee/specifications/persistence/3.1/)
- [Jakarta Persistence 3.2](https://jakarta.ee/specifications/persistence/3.2/)
- [Hibernate ORM — tài liệu theo phiên bản](https://hibernate.org/orm/documentation/)
- [EclipseLink — trang dự án và tài liệu](https://eclipse.dev/eclipselink/)
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Gradle — xem dependency graph](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
