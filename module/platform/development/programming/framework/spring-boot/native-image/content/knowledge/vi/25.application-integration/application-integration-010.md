# Flyway, Liquibase hoặc tài nguyên migration theo phiên bản hỗ trợ

## 1. Vì sao database migration cần được kiểm tra riêng khi build Native Image?

Ứng dụng Spring Boot thường phải cập nhật schema database trước khi các repository, JPA `EntityManagerFactory` hoặc service nghiệp vụ bắt đầu truy cập dữ liệu. Flyway, Liquibase và cơ chế SQL initialization của Spring Boot đều có thể thực hiện công việc này. Trên JVM, các công cụ migration thường tìm script trong classpath, phân tích changelog, tải driver database và thực thi SQL lúc ứng dụng khởi động.

Khi biên dịch ứng dụng thành **GraalVM Native Image**, classpath và tập resource được xác định tại build time. Các thao tác quét resource, nạp class theo tên, Java migration hoặc custom change có thể không được static analysis nhận biết đầy đủ. Một migration có thể tồn tại trong source tree nhưng không được đóng gói vào executable, hoặc đã được đóng gói nhưng công cụ migration không tìm thấy vì cách quét resource khác với JVM.

Spring Boot hỗ trợ tích hợp Flyway và Liquibase trong ứng dụng native, nhưng mức tương thích phụ thuộc vào phiên bản Spring Boot, phiên bản công cụ migration, database module/driver và cách tổ chức tài nguyên. Bài này tập trung vào cách chọn công cụ, đóng gói migration resources, cấu hình hints và kiểm thử trên executable native.

Sau bài học, bạn có thể:

- Cấu hình Flyway hoặc Liquibase bằng Spring Boot auto-configuration.
- Tổ chức SQL migration và changelog theo classpath để Native Image giữ được tài nguyên.
- Bổ sung `RuntimeHints` cho các thư mục migration hoặc file được tham chiếu động.
- Xử lý giới hạn Flyway Java migrations và resource scanning theo phiên bản Spring Boot.
- Dùng `schema.sql`/`data.sql` khi nhu cầu chỉ là khởi tạo đơn giản.
- Kiểm tra migration trên native executable, bao gồm cả file nằm trong thư mục con và các changelog được include.

## 2. Nguyên tắc chọn một cơ chế khởi tạo database

Spring Boot hỗ trợ nhiều cách tạo schema và dữ liệu ban đầu:

| Cơ chế | Phù hợp khi | Tài nguyên thường dùng |
|---|---|---|
| Flyway | Quản lý thay đổi schema theo migration có phiên bản và lịch sử thực thi | `db/migration/V1__create_orders.sql` |
| Liquibase | Quản lý changeSet, điều kiện, context/label và changelog nhiều định dạng | `db/changelog/db.changelog-master.yaml` |
| Spring SQL initialization | Ứng dụng nhỏ, demo, schema/data ban đầu đơn giản | `schema.sql`, `data.sql`, `schema-${platform}.sql` |

Nên chọn **một cơ chế chính** để quản lý schema. Spring Boot không khuyến nghị dùng `schema.sql`/`data.sql` song song với Flyway hoặc Liquibase; hỗ trợ phối hợp các cách khởi tạo cơ bản này sẽ bị loại bỏ trong tương lai. Nếu đã dùng công cụ migration, hãy để công cụ đó quản lý toàn bộ schema và dữ liệu khởi tạo.

Không dùng `spring.jpa.hibernate.ddl-auto=create`, `update` hoặc `create-drop` để cạnh tranh với migration trong môi trường production. Với ứng dụng dùng Flyway/Liquibase, thường đặt `ddl-auto=validate` hoặc `none` tùy cách triển khai.

## 3. Chuẩn bị resource và dependency theo Spring Boot version

### 3.1. Spring Boot 3.x và 4.x có cách đóng gói starter khác nhau

Tên artifact và package auto-configuration đã thay đổi giữa các major version. Dùng dependency management của Spring Boot để chọn version tương thích; không sao chép một version Flyway/Liquibase hoặc database driver từ ví dụ khác major version.

| Thành phần | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|
| Flyway | Thường dùng `org.flywaydb:flyway-core` cùng module database cần thiết | Có `spring-boot-starter-flyway`; thêm module database tương ứng |
| Liquibase | Dùng `org.liquibase:liquibase-core` | Có `spring-boot-starter-liquibase` |
| Flyway customizer package | `org.springframework.boot.autoconfigure.flyway` | `org.springframework.boot.flyway.autoconfigure` |
| Liquibase auto-configuration package | `org.springframework.boot.autoconfigure.liquibase` | `org.springframework.boot.liquibase.autoconfigure` |

Ví dụ dependency Maven cho Spring Boot 4.x với PostgreSQL:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
</dependencies>
```

Với Spring Boot 3.x, dependency cơ bản thường là:

```xml
<dependencies>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-core</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
</dependencies>
```

Ví dụ Liquibase trên Spring Boot 4.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-liquibase</artifactId>
</dependency>
```

Trên Spring Boot 3.x, dùng `org.liquibase:liquibase-core` và để Boot quản lý version. Nếu dự án đang ở một minor version cũ, hãy xem tài liệu đúng minor version để biết starter/artifact được cung cấp.

### 3.2. Giữ version do Spring Boot quản lý

Native support của Flyway trong Spring Boot có tích hợp với `NativeImageResourceProvider` và một số API scanner của Flyway. Vì vậy, việc tự override Flyway lên một minor version mới hơn BOM có thể làm hỏng auto-configuration native dù ứng dụng JVM vẫn hoạt động. Spring Boot duy trì hỗ trợ native cho Flyway với **version mặc định do Boot quản lý**; nếu override version, bạn phải tự chịu trách nhiệm tương thích và có thể cần cung cấp `ResourceProvider` riêng.

Quy tắc tương tự áp dụng cho Liquibase và database driver: kiểm tra dependency tree, dùng version tương thích mà Boot quản lý trước, chỉ override khi có lý do rõ ràng và đã chạy native integration tests.

Với Maven, kiểm tra version thực tế:

```bash
./mvnw dependency:tree \
  -Dincludes=org.flywaydb,org.liquibase,org.postgresql
```

Với Gradle:

```bash
./gradlew dependencyInsight \
  --dependency flyway-core \
  --configuration runtimeClasspath
```

Không suy ra khả năng native chỉ từ việc dependency resolve thành công hoặc JVM test chạy qua.

## 4. Flyway trong Spring Boot Native Image

### 4.1. Tổ chức SQL migrations trong classpath

Flyway mặc định tìm migration tại `classpath:db/migration`. Tên file versioned migration thường có dạng `V<VERSION>__<DESCRIPTION>.sql`:

```text
src/main/resources/
  db/
    migration/
      V1__create_orders.sql
      V2__add_order_status.sql
      R__refresh_order_summary.sql
```

Ví dụ `V1__create_orders.sql`:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    total_amount DECIMAL(18, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Ví dụ `V2__add_order_status.sql`:

```sql
ALTER TABLE orders
    ADD COLUMN status VARCHAR(24) NOT NULL DEFAULT 'PENDING';
```

Migration đã chạy trên môi trường dùng chung nên được xem là bất biến. Khi cần thay đổi schema, tạo file migration mới thay vì sửa nội dung migration cũ; Flyway lưu lịch sử trong bảng `flyway_schema_history`.

### 4.2. Cấu hình location và database

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST:localhost}:5432/orders
    username: ${DB_USER:orders_app}
    password: ${DB_PASSWORD:change-me}
  flyway:
    enabled: true
    locations:
      - classpath:db/migration
    validate-on-migrate: true
  jpa:
    hibernate:
      ddl-auto: validate
```

Nếu có migration riêng cho database vendor, có thể dùng placeholder `{vendor}`:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,classpath:db/migration/{vendor}
```

Hoặc cấu hình trực tiếp một thư mục migration ngoài executable:

```yaml
spring:
  flyway:
    locations: classpath:db/migration,filesystem:/opt/orders/migrations
```

`classpath:` trỏ tới resource được đóng gói trong native image; `filesystem:` trỏ tới file thật trên filesystem lúc ứng dụng chạy. File ngoài image không cần resource hint, nhưng phải được mount/copy vào container và quyền đọc phải phù hợp.

### 4.3. Resource hints cho Flyway

Spring Boot có cơ chế hỗ trợ Flyway classpath scanning khi chạy native. Nếu dùng location mặc định, hãy bắt đầu với auto-configuration và version do Boot quản lý. Nếu migration ở location tùy chỉnh hoặc native executable báo thiếu resource, có thể bổ sung hint tường minh:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class OrderMigrationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/migration/**");
        hints.resources().registerPattern("db/migration-extra/**");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderMigrationRuntimeHints.class)
class OrderMigrationNativeConfiguration {
}
```

Pattern `**` bao gồm file trong các thư mục con. Đăng ký đúng gốc classpath, không thêm `src/main/resources/` vào pattern. Nếu dùng location khác, hãy đăng ký pattern tương ứng với đúng resource được truy cập.

Lưu ý: resource hint chỉ bảo đảm file được giữ trong image. Nó không sửa một lỗi runtime scanner của Flyway và không bảo đảm mọi phiên bản Flyway tương thích với `NativeImageResourceProvider` của Boot. Với migration lồng nhiều cấp, cần dùng bản Spring Boot có fix quét subdirectory và chạy test xác nhận từng migration thực sự được phát hiện.

### 4.4. Giới hạn của Java-based migrations

Flyway hỗ trợ SQL migration và Java migration. Tuy nhiên, **tự động phát hiện Java migrations không được hỗ trợ đầy đủ trong Spring Boot Native Image**. Nếu dự án cần Java migration, đăng ký các instance migration tường minh bằng `FlywayConfigurationCustomizer` thay vì trông chờ classpath scanning.

Ví dụ cho Spring Boot 4.x:

```java
package com.example.orders.config;

import org.springframework.boot.flyway.autoconfigure.FlywayConfigurationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import db.migration.V3__BackfillOrderStatus;

@Configuration(proxyBeanMethods = false)
class FlywayJavaMigrationConfiguration {

    @Bean
    FlywayConfigurationCustomizer registerJavaMigrations() {
        return configuration -> configuration.javaMigrations(
                new V3__BackfillOrderStatus());
    }
}
```

Class migration được đăng ký ở trên phải có mặt trong application classpath. Ví dụ rút gọn:

```java
package db.migration;

import java.sql.PreparedStatement;

import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

public class V3__BackfillOrderStatus extends BaseJavaMigration {

    @Override
    public void migrate(Context context) throws Exception {
        try (PreparedStatement statement = context.getConnection().prepareStatement(
                "UPDATE orders SET status = 'PENDING' WHERE status IS NULL")) {
            statement.execute();
        }
    }
}
```

Chỉ đóng `PreparedStatement`; không đóng connection do Flyway cấp qua `Context`.

Trên Spring Boot 3.x, import `FlywayConfigurationCustomizer` từ package `org.springframework.boot.autoconfigure.flyway`. Cả hai ví dụ đều giả định class `V3__BackfillOrderStatus` có mặt trong application classpath và có thể được tạo ở build time.

Ưu tiên SQL migrations nếu thay đổi có thể biểu diễn bằng SQL. Nếu Java migration thực hiện reflection, tải resource động hoặc dùng class được xác định theo tên, bạn vẫn cần kiểm tra các runtime hints tương ứng. Việc đăng ký migration instance không tự động cung cấp mọi reflection/resource hint mà phần code bên trong migration cần.

### 4.5. Những cảnh báo và cờ build có thể gặp

Spring Boot Native Image wiki ghi nhận một số hành vi theo version:

- Flyway có thể ghi cảnh báo `Unable to scan location: /db/migration (unsupported protocol: resource)` khi dùng native resource provider. Đây có thể là cảnh báo từ đường quét resource JVM không được dùng trong native; chỉ bỏ qua sau khi xác nhận migration đã được phát hiện và áp dụng bằng cách kiểm tra `flyway_schema_history` và schema thực tế.
- Từ Flyway 12.3, Flyway có thể tạo URL `https://` trong startup. GraalVM mặc định không bật mọi URL protocol; nếu native build thất bại với lỗi `Accessing a URL protocol that was not enabled`, thêm `--enable-url-protocols=https` vào build arguments.
- Một số bản Spring Boot có lỗi phát hiện migration trong thư mục con. Spring Boot 3.5.13 đã có bản sửa cho `NativeImageResourceProvider`; kiểm tra release note của đúng nhánh Boot đang dùng trước khi triển khai.

Ví dụ Gradle Native Build Tools khi cần bật HTTPS:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--enable-url-protocols=https')
        }
    }
}
```

Với Maven Native Build Tools, truyền cùng option trong `buildArgs` của `native-maven-plugin`:

```xml
<configuration>
    <buildArgs>
        <buildArg>--enable-url-protocols=https</buildArg>
    </buildArgs>
</configuration>
```

Chỉ thêm option khi dependency/version thực tế cần nó hoặc build báo lỗi URL protocol. Không dùng tùy chọn này để che một lỗi scanner hoặc thiếu migration resource.

## 5. Liquibase trong Spring Boot Native Image

### 5.1. Tổ chức changelog và các file được include

Liquibase mặc định đọc master changelog tại:

```text
classpath:db/changelog/db.changelog-master.yaml
```

Các định dạng changelog được hỗ trợ gồm YAML, XML, JSON và SQL. Có thể chia changeset thành các file riêng rồi include từ master:

```text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-orders.yaml
        002-add-order-status.yaml
      sql/
        seed-order-types.sql
```

Ví dụ master changelog:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-order-status.yaml
      relativeToChangelogFile: true
```

Một changelog có thể tham chiếu file SQL bằng `sqlFile`:

```yaml
databaseChangeLog:
  - changeSet:
      id: seed-order-types
      author: orders-team
      changes:
        - sqlFile:
            path: ../sql/seed-order-types.sql
            relativeToChangelogFile: true
            splitStatements: true
```

`relativeToChangelogFile: true` giúp đường dẫn được giải quyết tương đối theo changelog đang chứa tham chiếu. Hãy giữ file được tham chiếu trong `src/main/resources` để nó được đóng gói cùng ứng dụng.

### 5.2. Cấu hình Liquibase

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${DB_HOST:localhost}:5432/orders
    username: ${DB_USER:orders_app}
    password: ${DB_PASSWORD:change-me}
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
    contexts: production
  jpa:
    hibernate:
      ddl-auto: validate
```

Spring Boot tự cấu hình `SpringLiquibase` khi starter/dependency Liquibase có mặt và dùng `DataSource` chính nếu không có cấu hình datasource riêng. Changelog được áp dụng khi context khởi động; nếu cần điều khiển `contexts`, `labels`, schema hoặc changelog path, cấu hình qua `spring.liquibase.*`.

### 5.3. Đảm bảo toàn bộ changelog resources có trong native image

Liquibase cần cả master changelog và mọi file được tham chiếu qua `include`, `includeAll`, `sqlFile` hoặc các resource khác. Spring Boot có runtime hints cơ bản cho Liquibase, nhưng với cấu trúc changelog tùy chỉnh, cần kiểm tra resource config do AOT sinh và chạy native integration test để xác nhận các file con được tìm thấy.

Nếu thiếu file được include, có thể bổ sung hint theo thư mục sở hữu:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;
import com.example.orders.db.NormalizeOrderCodes;

class LiquibaseChangelogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/changelog/**");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LiquibaseChangelogRuntimeHints.class)
class LiquibaseNativeConfiguration {
}
```

Pattern này bao gồm master file, changelog con, SQL file và resource nằm trong các thư mục con. Nếu dự án lưu changelog ở một gốc khác, thay pattern cho đúng đường dẫn classpath. Không đăng ký toàn bộ `**/*` của ứng dụng nếu chỉ có một thư mục migration cần giữ.

### 5.4. Custom change và class được nạp theo tên

Liquibase có thể sử dụng custom change, custom precondition, `includeAll` với resource filter/comparator hoặc extension được nạp theo tên class. Những class này không chỉ là resource; chúng còn cần reachable/reflection metadata khi được khởi tạo động.

Ví dụ một custom change:

```java
package com.example.orders.db;

import liquibase.change.custom.CustomTaskChange;
import liquibase.database.Database;
import liquibase.exception.CustomChangeException;
import liquibase.exception.SetupException;
import liquibase.exception.ValidationErrors;
import liquibase.resource.ResourceAccessor;

public class NormalizeOrderCodes implements CustomTaskChange {

    @Override
    public void execute(Database database) throws CustomChangeException {
        // Thực hiện thay đổi dữ liệu bằng API Liquibase/JDBC phù hợp.
    }

    @Override
    public void setUp() throws SetupException {
    }

    @Override
    public void setFileOpener(ResourceAccessor resourceAccessor) {
    }

    @Override
    public ValidationErrors validate(Database database) {
        return new ValidationErrors();
    }

    @Override
    public String getConfirmationMessage() {
        return "Order codes normalized";
    }
}
```

Nếu custom class được tham chiếu bằng tên trong changelog, đăng ký reflection hints cho class đó khi native build báo thiếu metadata:

```java
package com.example.orders.config;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class LiquibaseCustomChangeRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                NormalizeOrderCodes.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LiquibaseCustomChangeRuntimeHints.class)
class LiquibaseCustomChangeConfiguration {
}
```

Không thêm reflection hints cho tất cả class trong package theo thói quen. Hãy xác định chính xác class nào được Liquibase nạp động, constructor và method nào cần được gọi.

## 6. SQL resources của Spring Boot khi không cần Flyway/Liquibase

### 6.1. `schema.sql` và `data.sql`

Với ứng dụng nhỏ hoặc database dùng cho demo/test, Spring Boot có thể chạy script cơ bản:

```text
src/main/resources/
  db/
    schema.sql
    data.sql
```

Ví dụ:

```sql
-- schema.sql
CREATE TABLE feature_flag (
    flag_key VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN NOT NULL
);
```

```sql
-- data.sql
INSERT INTO feature_flag(flag_key, enabled)
VALUES ('order-export', TRUE);
```

Mặc định, Spring Boot chỉ tự khởi tạo SQL script cho embedded database. Để chạy với database khác, đặt:

```yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:db/schema.sql
      data-locations: classpath:db/data.sql
```

Để tắt cơ chế này, đặt `spring.sql.init.mode=never`. Cơ chế này không có lịch sử versioned migration như Flyway hoặc Liquibase; nếu cần quản lý thay đổi schema qua nhiều bản phát hành, nên dùng một migration tool chuyên dụng.

### 6.2. Resource hints cho script tùy chỉnh

Nếu script được cấu hình bằng đường dẫn động hoặc không được Spring AOT nhận biết, có thể đăng ký resource hints:

```java
package com.example.orders.config;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

class SqlInitializationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("db/schema.sql");
        hints.resources().registerPattern("db/data.sql");
    }
}

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SqlInitializationRuntimeHints.class)
class SqlInitializationNativeConfiguration {
}
```

Kiểm tra generated resource metadata trong output AOT trước khi thêm hints thủ công. Với path constant được Spring Boot nhận biết, framework hoặc GraalVM có thể đã suy ra được resource cần giữ.

### 6.3. Script theo database platform

Spring Boot hỗ trợ file theo platform:

```text
schema-postgresql.sql
data-postgresql.sql
schema-mysql.sql
data-mysql.sql
```

Cấu hình `spring.sql.init.platform=postgresql` để chọn script tương ứng. Các file vẫn là classpath resources và phải có mặt trong native image. Nếu ứng dụng build thành nhiều native artifact theo database, mỗi artifact cần đóng gói đúng tập script của platform đó.

## 7. Chọn classpath hay filesystem cho migration

| Cách đặt migration | Được đóng gói trong native image? | Khi nên dùng | Điều cần kiểm tra |
|---|---|---|---|
| `classpath:db/migration` | Có, nếu resource được đưa vào image | Migration phát hành cùng phiên bản ứng dụng | Resource hints, scanner và file trong thư mục con |
| `classpath:db/changelog/...` | Có, nếu changelog và mọi file include được đưa vào image | Liquibase changelog versioned cùng ứng dụng | Master, include, includeAll, sqlFile, custom change |
| `filesystem:/opt/migrations` | Không; file nằm ngoài executable | Muốn triển khai migration độc lập hoặc mount từ pipeline | File tồn tại trong container, quyền đọc và đường dẫn cấu hình |
| `schema.sql`/`data.sql` | Có, nếu script được giữ như classpath resource | Khởi tạo schema/data đơn giản | `spring.sql.init.mode`, platform và resource hints |

Classpath resources tạo ra một artifact có migration gắn với đúng phiên bản ứng dụng. Filesystem resources cho phép thay migration mà không rebuild native image, nhưng khi đó schema có thể thay đổi độc lập với code. Cần quản lý quyền ghi/đọc và kiểm soát phiên bản migration chặt chẽ.

## 8. Tránh chạy nhiều cơ chế migration cùng lúc

Không nên để Flyway và Liquibase cùng quản lý một schema, hoặc để Hibernate `ddl-auto=update` cạnh tranh với migration. Việc có nhiều công cụ cùng thay đổi cấu trúc bảng khiến lịch sử và trạng thái database khó dự đoán.

Một cấu hình điển hình:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
  liquibase:
    enabled: false
  sql:
    init:
      mode: never
```

Nếu chọn Liquibase, đảo trạng thái `flyway.enabled` và `liquibase.enabled`. Không cần khai báo cả hai prefix nếu dependency tương ứng không có trong ứng dụng; ví dụ trên chỉ minh họa cách loại trừ cơ chế còn lại.

Spring Boot nhận diện Flyway/Liquibase như database initializer và sắp xếp các bean phụ thuộc database chạy sau khi khởi tạo hoàn tất. Với bean tùy chỉnh cần schema đã được migrate, có thể dùng `@DependsOnDatabaseInitialization` nếu auto-detection không nhận ra dependency đó.

## 9. Migration trong ứng dụng native: chạy lúc startup hay thành job riêng?

Spring Boot có thể chạy Flyway/Liquibase khi application context khởi động. Đây là lựa chọn đơn giản cho ứng dụng nhỏ hoặc môi trường triển khai chỉ có một instance. Tuy nhiên, trong production có nhiều replica, migration cần quyền DDL và có thể làm chậm thời gian readiness.

Hai hướng triển khai thường gặp:

| Mô hình | Cách thực hiện | Ưu điểm | Cần kiểm soát |
|---|---|---|---|
| Migration khi app startup | Native executable chạy migration trước khi phục vụ request | Artifact tự bảo đảm schema cần thiết trước khi chạy code | Quyền DDL, lock, startup/readiness, nhiều replica |
| Migration job riêng | Chạy migration trong job/init container hoặc pipeline trước khi rollout app | Tách quyền migration khỏi quyền runtime, dễ quan sát và rollback release | Job phải hoàn tất trước khi app mới nhận traffic |

Flyway dùng schema history và lock để điều phối migration; Liquibase dùng bảng `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`. Các cơ chế này hỗ trợ đồng bộ, nhưng không thay thế quy trình release và giám sát khi nhiều replica khởi động cùng lúc.

Một cách triển khai an toàn là dùng user database riêng cho migration có quyền DDL, còn user runtime chỉ có quyền cần thiết để đọc/ghi dữ liệu. Nếu migration job riêng đã chạy, cấu hình ứng dụng không chạy migration startup lần nữa hoặc dùng cơ chế phù hợp để xác nhận schema đã đúng.

## 10. Kiểm thử migration trên Native Image

### 10.1. Kiểm tra trước khi build native

1. Chạy migration trên JVM với database cùng loại/version với production.
2. Kiểm tra tên file, changelog path, `include`, `includeAll` và `sqlFile`.
3. Kiểm tra dependency tree để bảo đảm Flyway/Liquibase và JDBC driver được Boot quản lý đúng.
4. Chạy Spring AOT và xem resource hints đã chứa migration/changelog cần thiết chưa.
5. Nếu dùng Java migration hoặc custom change, kiểm tra class đã được đăng ký rõ ràng và có reflection hints cần thiết.

### 10.2. Chạy native executable trên database sạch

Build native executable/container image theo quy trình của dự án. Dùng một database sạch, sau đó chạy executable và xác nhận:

- Ứng dụng khởi động thành công.
- Flyway tạo `flyway_schema_history` hoặc Liquibase tạo `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.
- Tất cả versioned migration/changeset mong đợi đã được áp dụng.
- Các bảng, index, constraint và dữ liệu seed có mặt.
- File migration trong thư mục con và mọi file include đều được tìm thấy.

### 10.3. Chạy lại và nâng cấp từ schema cũ

Không chỉ kiểm tra lần đầu. Chạy lại native executable trên cùng database để xác nhận migration không bị áp dụng lặp. Sau đó tạo database ở version cũ, chạy executable mới và xác nhận migration nâng cấp chạy theo thứ tự.

Đối với Flyway, kiểm tra `flyway_schema_history` và kết quả `validate`. Đối với Liquibase, kiểm tra `DATABASECHANGELOG` và checksum của changeset. Nếu có SQL init, kiểm tra dữ liệu/schema đã tồn tại và fail-fast khi script lỗi.

### 10.4. Test tài nguyên và cấu hình riêng

Tối thiểu nên có các trường hợp:

- Migration mặc định ở thư mục gốc.
- Migration nằm trong một hoặc nhiều thư mục con.
- Changelog include file SQL/YAML/XML khác.
- Location tùy chỉnh hoặc `{vendor}`.
- Migration được cấu hình bằng filesystem path nếu sử dụng.
- Database driver đúng nền tảng native target.
- Migration thất bại phải làm application/job trả trạng thái lỗi rõ ràng.

Native build thành công chưa chứng minh migration resource đã được tìm thấy. Chỉ native integration test chạy trên database thật hoặc môi trường database tương đương mới xác nhận được đường migration.

## 11. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Flyway báo không có migration trên native | Resource không được đóng gói hoặc scanner không tìm thấy resource | Kiểm tra `spring.flyway.locations`, resource metadata, Boot-managed Flyway version và `flyway_schema_history` |
| Flyway báo `unsupported protocol: resource` | Cảnh báo từ đường quét resource JVM khi native dùng provider riêng | Chỉ bỏ qua sau khi xác nhận migrations được phát hiện và chạy; kiểm tra log và bảng history |
| Flyway không tìm thấy file trong thư mục con | Bản Spring Boot chưa có fix recursive resource discovery hoặc resource provider flatten path | Dùng bản Boot có fix (Boot 3.5.13 trở lên cho nhánh 3.5) và kiểm thử subdirectory trên native |
| `NoSuchMethodError` trong `NativeImageResourceProviderCustomizer` | Flyway bị override sang version không tương thích với Boot | Quay về version do Boot BOM quản lý hoặc tự cung cấp `ResourceProvider` tương thích qua `FlywayConfigurationCustomizer` |
| Flyway không tự tìm Java migration | Automatic detection không được hỗ trợ trong native | Đăng ký instance bằng `FlywayConfigurationCustomizer` và kiểm tra reflection hints bên trong migration |
| Native build báo URL protocol `https` chưa bật | Flyway từ 12.3 tạo HTTPS URL trong startup, GraalVM chưa bật protocol | Thêm `--enable-url-protocols=https` nếu đúng lỗi này xuất hiện |
| Liquibase tìm thấy master nhưng thiếu file include | Changelog con/SQL file chưa được giữ trong image hoặc path include sai | Đăng ký `db/changelog/**`, kiểm tra `relativeToChangelogFile` và generated resource metadata |
| Liquibase không tạo custom change | Class được tham chiếu bằng tên nhưng thiếu reflection/constructor metadata | Đăng ký class và member cần thiết bằng `RuntimeHintsRegistrar` |
| SQL init chạy trên JVM nhưng không chạy native | Script không có trong image hoặc `spring.sql.init.mode` đang là `embedded` | Đặt `mode=always` nếu cần, kiểm tra resource hints và native log |
| Migration chạy trước khi database sẵn sàng | Database connection chưa sẵn sàng hoặc deployment chưa có dependency | Kiểm tra readiness/connection retry và sắp xếp migration job trước app rollout |
| Hai công cụ cùng thay đổi schema | Flyway, Liquibase, SQL init hoặc Hibernate DDL cùng bật | Chỉ chọn một cơ chế schema initialization; đặt `ddl-auto=validate`/`none` |
| Native app khởi động thất bại khi DB user thiếu quyền | Runtime user không có quyền DDL hoặc migration job chưa chạy | Dùng migration user/job riêng hoặc cấp quyền có kiểm soát |

## 12. Bài thực hành: đóng gói Flyway và Liquibase resources

**Bối cảnh:** dịch vụ `order-service` dùng PostgreSQL và cần tạo bảng `orders`, sau đó thêm cột `status`. Bạn sẽ thử hai biến thể: Flyway SQL migrations và Liquibase changelog.

### Phương án A — Flyway

1. Thêm starter/module Flyway đúng với Spring Boot version và PostgreSQL driver module.
2. Tạo `V1__create_orders.sql` và `V2__add_order_status.sql` trong `src/main/resources/db/migration`.
3. Cấu hình `spring.flyway.locations=classpath:db/migration`.
4. Giữ Flyway version do Spring Boot BOM quản lý.
5. Nếu dùng migration trong thư mục con, xác nhận Spring Boot patch có recursive resource fix.
6. Build native, chạy với PostgreSQL sạch và kiểm tra `flyway_schema_history`.

### Phương án B — Liquibase

1. Thêm Liquibase starter/dependency theo Spring Boot version.
2. Tạo `db.changelog-master.yaml` và các file được include trong `db/changelog`.
3. Cấu hình `spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml`.
4. Kiểm tra Boot hints; bổ sung `db/changelog/**` nếu changelog con chưa được giữ.
5. Build native, chạy với PostgreSQL sạch và kiểm tra `DATABASECHANGELOG`.

### Phương án C — SQL initialization đơn giản

1. Tạo `db/schema.sql` và `db/data.sql` trong classpath.
2. Đặt `spring.sql.init.mode=always` nếu dùng database không embedded.
3. Kiểm tra resource metadata của hai file.
4. Chạy native executable và xác nhận schema/data được tạo.

### Phiếu kết quả

| Hạng mục | Kết quả cần ghi |
|---|---|
| Spring Boot version | _(ghi)_ |
| Migration tool/version | Flyway / Liquibase / SQL init |
| Database và driver version | _(ghi)_ |
| Classpath locations | _(ghi)_ |
| Resource hints | _(ghi pattern)_ |
| Migration ở thư mục con | PASS/FAIL |
| Changelog include/sqlFile | PASS/FAIL |
| Native build | PASS/FAIL |
| Migration trên DB sạch | PASS/FAIL |
| Chạy lại không áp dụng trùng | PASS/FAIL |
| Nâng cấp từ schema cũ | PASS/FAIL |

## 13. Ghi nhớ

Flyway, Liquibase và SQL initialization đều có thể dùng trong Spring Boot Native Image nếu công cụ, version, driver và migration resources tương thích. Hãy dùng version do Spring Boot quản lý, giữ file migration trong classpath khi muốn đóng gói cùng executable, và bổ sung resource/reflection hints cho những file hoặc class được truy cập động mà AOT chưa suy ra.

Flyway SQL migrations thường là lựa chọn đơn giản nhất cho native. Java migrations cần đăng ký tường minh bằng `FlywayConfigurationCustomizer`; Flyway native integration phụ thuộc chặt vào version Flyway do Boot quản lý. Liquibase cần bảo đảm toàn bộ changelog include và SQL resources có mặt trong image, không chỉ master changelog. Với script đơn giản, Spring SQL initialization là lựa chọn nhẹ hơn, nhưng không thay thế được lịch sử migration versioned. Chỉ một cơ chế nên chịu trách nhiệm tạo và cập nhật schema.

### Tài liệu tham khảo chính thức

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — GraalVM Native Image Compatibility Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-with-GraalVM)
- [Spring Boot — FlywayConfigurationCustomizer API (4.x)](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/flyway/autoconfigure/FlywayConfigurationCustomizer.html)
- [Spring Boot — LiquibaseAutoConfiguration API (4.x)](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/liquibase/autoconfigure/LiquibaseAutoConfiguration.html)
- [Redgate Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Redgate Flyway — Java-based Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/java-based-migrations)
- [Spring Boot issue — Flyway Java migrations and Native Image](https://github.com/spring-projects/spring-boot/issues/33458)
- [Spring Boot issue — Flyway NativeImageResourceProvider and subdirectories](https://github.com/spring-projects/spring-boot/issues/49661)
- [Spring Boot issue — Flyway version compatibility with Native Image](https://github.com/spring-projects/spring-boot/issues/47368)
- [Spring Boot issue — Liquibase changelog resource hints](https://github.com/spring-projects/spring-boot/issues/34678)
- [Liquibase — CustomTaskChange API](https://javadocs.liquibase.com/liquibase-core/liquibase/change/custom/CustomTaskChange.html)
