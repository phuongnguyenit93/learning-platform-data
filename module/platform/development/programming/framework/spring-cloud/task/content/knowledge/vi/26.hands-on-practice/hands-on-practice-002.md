# Nhập tệp CSV với PostgreSQL và lịch sử thực thi bền vững

Trong chương **Thực hành** của module **SPRING_CLOUD_TASK**, chúng ta xây dựng một ứng dụng Spring Boot chạy một lần, đọc dữ liệu từ **CSV**, kiểm tra hợp lệ, lưu vào **PostgreSQL** rồi kết thúc. Sau khi JVM thoát, người vận hành vẫn xem được **lịch sử thực thi** qua `TaskRepository`: mỗi lần chạy bắt đầu khi nào, kết thúc khi nào, mã thoát là gì và có lỗi hay không.

Bài thực hành còn giải quyết yêu cầu quan trọng của hệ thống chạy theo lịch hoặc theo yêu cầu: **chạy lại cùng một tệp không được nhập trùng dữ liệu**. Nếu JVM dừng ngay sau khi PostgreSQL đã commit nhưng trước khi Task kịp báo hoàn tất, lần chạy tiếp theo phải phát hiện dữ liệu đã có và kết thúc an toàn.

Ta sẽ làm một ứng dụng `csv-import-task` có các đặc điểm:

- Nhận các tham số `--input`, `--tenant`, `--businessDate`, `--sourceVersion` và `--runId`.
- Đọc CSV đúng cú pháp có dấu phẩy/nháy kép bằng **Apache Commons CSV**; không dùng `String.split(",")`.
- Kiểm tra header, mã giao dịch, số tiền `BigDecimal`, loại tiền và ID trùng trong tệp.
- Tạo checksum **SHA-256 từ đúng bytes đã được parse** để xác định nội dung tệp.
- Dùng transaction JDBC và khóa chính PostgreSQL để đảm bảo **nhập trọn bộ hoặc rollback**, kể cả khi có lỗi giữa chừng.
- Ghi metadata của **mỗi lần thực thi** trong bảng `TASK_EXECUTION` của Spring Cloud Task; bảng dữ liệu nghiệp vụ có cơ chế kiểm soát trùng riêng.
- Có bài thử cho nhập lại, tệp bị sửa, dữ liệu sai, lỗi giữa transaction và restart PostgreSQL.

**Phạm vi:** ví dụ này dành cho tệp nhỏ (tối đa **4 MiB, 10.000 dòng dữ liệu**), phù hợp để học và tự chạy. Khi nhập hàng triệu dòng, cần chuyển sang đọc dạng streaming/chunk hoặc Spring Batch, được phân tích ở cuối bài.

## 1. Mục tiêu và kết quả nghiệm thu

Sau bài này, bạn có thể:

1. Khởi động PostgreSQL có volume bền vững trên máy phát triển.
2. Tạo ứng dụng Spring Cloud Task với `ApplicationRunner` và `TaskRepository` JDBC.
3. Viết parser CSV kiểm tra dữ liệu trước khi mở transaction.
4. Thiết kế schema có **khóa nghiệp vụ**, checksum và ràng buộc toàn vẹn.
5. Áp dụng `@Transactional` với `JdbcTemplate` và `INSERT ... ON CONFLICT DO NOTHING`.
6. Phân biệt record trong `TASK_EXECUTION` với dữ liệu nhập trong các bảng nghiệp vụ.
7. Kiểm chứng sau khi JVM thoát hoặc PostgreSQL được stop/start.
8. Xử lý an toàn khi import bị thử lại, lỗi validation, mất kết nối và kết quả commit chưa xác định.
9. Biết khi nào nên dùng Spring Batch để hỗ trợ checkpoint, chunk và restart.

### Tiêu chí hoàn tất

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| CSV hợp lệ, lần đầu | 3 dòng được nhập, lần chạy Task ghi nhận hoàn tất |
| Nhập lại cùng business key và cùng bytes | Không thêm dòng, ứng dụng báo `ALREADY_APPLIED` |
| Cùng business key nhưng nội dung tệp khác | Báo `IDEMPOTENCY_CONFLICT`, không ghi đè kết quả cũ |
| CSV có dữ liệu sai | Không tạo kết quả nghiệp vụ, Task ghi nhận lỗi nếu repository còn hoạt động |
| Lỗi sau khi ghi dòng đầu tiên nhưng trước commit | Rollback cả ledger và các dòng đã ghi |
| JVM thoát, chạy lại hoặc PostgreSQL được restart | Lịch sử và kết quả vẫn tồn tại trong PostgreSQL |
| Nhiều lần chạy với cùng một yêu cầu | Có thể có nhiều `TaskExecution`, nhưng **chỉ một bộ kết quả nghiệp vụ** |

## 2. Kiến trúc và luồng thực thi

~~~mermaid
flowchart TD
    A["Scheduler / CLI: business key + đường dẫn CSV"] --> B["Spring Boot ApplicationRunner"]
    B --> C["Đọc một snapshot bytes của tệp"]
    C --> D["Parse CSV, validate và tính SHA-256"]
    D -->|"Sai"| E["Ném exception, task thất bại"]
    D -->|"Hợp lệ"| F["ImportService @Transactional"]
    F --> G{"Đã có ledger theo business key?"}
    G -->|"Chưa"| H["INSERT ledger + INSERT rows cùng transaction"]
    G -->|"Có, cùng hash"| I["ALREADY_APPLIED"]
    G -->|"Có, hash khác"| J["IDEMPOTENCY_CONFLICT"]
    H --> K["COMMIT PostgreSQL"]
    K --> L["Runner hoàn tất"]
    I --> L
    J --> E
    L --> M["Spring Cloud Task cập nhật TaskRepository"]
    E --> M
    M --> N["JVM kết thúc; lịch sử còn trong PostgreSQL"]
~~~

Hai loại dữ liệu **không được lẫn nhau**:

| Nguồn | Ví dụ bảng | Mục đích |
| --- | --- | --- |
| **Metadata Spring Cloud Task** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_SEQ` | Theo dõi **mỗi lần chạy tiến trình**: thời gian, exit code, thông điệp |
| **Dữ liệu nghiệp vụ** | `csv_import`, `sales_line` | Xác định **công việc nhập CSV** đã được thực hiện chưa và những dòng nào đã commit |

Một yêu cầu có thể chạy hai hoặc ba lần do timeout hoặc scheduler retry. `TASK_EXECUTION_ID` mỗi lần khác nhau, nhưng khóa nghiệp vụ `(tenant_id, business_date, source_version)` phải **giữ nguyên** nếu đó là cùng một công việc.

## 3. Công cụ và phiên bản mẫu

Cần có:

- **JDK 17+**, Maven hoặc Maven Wrapper; Docker Desktop/Engine để khởi động PostgreSQL.
- PostgreSQL 16 (ảnh Docker minh họa), một cổng TCP không trùng cổng khác.
- Spring Boot **3.5.x** cùng Spring Cloud release train **2025.0.x**, vốn được công bố tương thích; chọn đúng patch từ tài liệu chính thức.
- Spring Cloud Task, `spring-boot-starter-jdbc`, PostgreSQL JDBC Driver và Apache Commons CSV.
- Một công cụ SQL tùy chọn như `psql`, DBeaver hoặc DataGrip.

Để các đoạn Maven có một baseline cụ thể, ví dụ bên dưới chọn **Spring Boot 3.5.13 + Spring Cloud 2025.0.2** (tổ hợp được thông báo cùng release train), Java 17 và Commons CSV 1.14.1. Các số này là **baseline minh họa**, không mặc định là phiên bản mới nhất hay phù hợp với mọi dự án năm 2026. Nếu dự án dùng Spring Boot 4, hãy chọn train tương ứng và kiểm tra thay đổi API.

## 4. Chuẩn bị PostgreSQL bền vững

### 4.1. Khởi động container với named volume

Trên máy phát triển, chạy lệnh một dòng:

~~~bash
docker run -d --name csv-task-postgres -e POSTGRES_DB=taskdemo -e POSTGRES_USER=taskdemo -e POSTGRES_PASSWORD=local-demo-only -p 5433:5432 -v csv_task_pgdata:/var/lib/postgresql/data postgres:16
~~~

Lệnh dùng:

- Cổng host `5433` để tránh trùng PostgreSQL đang nghe ở `5432`; bên trong container vẫn là `5432`.
- Database và user tên `taskdemo`.
- Volume `csv_task_pgdata` để dữ liệu **không mất khi container dừng và được khởi động lại**.
- Mật khẩu `local-demo-only` **chỉ dành cho localhost trong bài học**; không đưa mật khẩu thật vào command line, Git hoặc log production.

Kiểm tra DB đã sẵn sàng:

~~~bash
docker exec csv-task-postgres pg_isready -U taskdemo -d taskdemo
~~~

Mong đợi thông báo database chấp nhận kết nối. Nếu port `5433` đã được dùng, chọn cổng host khác và cập nhật JDBC URL tương ứng.

### 4.2. Mở trình SQL trong container

~~~bash
docker exec -it csv-task-postgres psql -U taskdemo -d taskdemo
~~~

Các câu SQL ở các mục tiếp theo được chạy trong prompt `psql` hoặc một SQL client đang kết nối tới `localhost:5433/taskdemo`. **Không xóa volume hoặc reset database khi cần kiểm chứng tính bền vững.**

## 5. Tạo schema nghiệp vụ

Chúng ta tạo hai bảng. Bảng `csv_import` đóng vai trò **ledger/idempotency record** của một kỳ nhập tệp; bảng `sales_line` chứa kết quả.

~~~sql
CREATE TABLE csv_import (
    tenant_id      VARCHAR(64)  NOT NULL,
    business_date  DATE         NOT NULL,
    source_version VARCHAR(32)  NOT NULL,
    input_sha256   CHAR(64)     NOT NULL,
    row_count      INTEGER      NOT NULL CHECK (row_count > 0),
    completed_at   TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, business_date, source_version)
);

CREATE TABLE sales_line (
    tenant_id      VARCHAR(64)  NOT NULL,
    business_date  DATE         NOT NULL,
    source_version VARCHAR(32)  NOT NULL,
    external_id    VARCHAR(64)  NOT NULL,
    amount         NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency       CHAR(3)      NOT NULL CHECK (currency = 'USD'),
    PRIMARY KEY (
        tenant_id, business_date, source_version, external_id
    ),
    FOREIGN KEY (tenant_id, business_date, source_version)
        REFERENCES csv_import (
            tenant_id, business_date, source_version
        )
);
~~~

**Ý nghĩa các ràng buộc:**

- `PRIMARY KEY (tenant_id, business_date, source_version)` bảo vệ một lần nhập hợp lệ cho một kỳ và phiên bản.
- `input_sha256` cho phép so sánh lần import mới với **toàn bộ bytes của tệp cũ**. Cùng key nhưng khác bytes phải báo conflict.
- `row_count` ghi số dòng mà ứng dụng cam kết lưu trong transaction.
- Khóa chính của `sales_line` ngăn hai dòng trùng `external_id` cùng kỳ.
- Foreign key ngăn dòng bán hàng không liên kết tới ledger.
- `NUMERIC(18,2)` và `BigDecimal` tránh sai số kiểu `double` đối với tiền.

**Không tự tạo** `TASK_EXECUTION` bằng DDL ở trên. Các bảng `TASK_*` được Spring Cloud Task tạo theo **schema đúng phiên bản framework** khi cho phép initializer, hoặc được DBA/migration tạo trước. Hai nhóm bảng cùng ở PostgreSQL trong bài này, nhưng không có nghĩa hai thời điểm cập nhật metadata và dữ liệu nghiệp vụ thuộc cùng transaction.

### Kiểm tra ban đầu

~~~sql
SELECT COUNT(*) FROM csv_import;
SELECT COUNT(*) FROM sales_line;
~~~

Cả hai giá trị dự kiến bằng `0` trên database mới. Chỉ chạy bài này ở database **cô lập**; không xóa dữ liệu của các dự án khác.

## 6. Chuẩn bị CSV UTF-8

Tạo file `data/sales-2026-11-24.csv` (UTF-8 **không BOM**) với nội dung:

~~~csv
external_id,amount,currency
S-001,10.50,USD
S-002,"22.00",USD
S-003,3.25,USD
~~~

Các quy tắc contract:

| Trường CSV | Kiểu sau parse | Ràng buộc |
| --- | --- | --- |
| `external_id` | `String` | `A-Z`, `0-9`, dấu gạch ngang/gạch dưới, tối đa 64 ký tự; không trùng trong cùng tệp |
| `amount` | `BigDecimal` | Lớn hơn 0, tối đa 2 chữ số thập phân, vừa `NUMERIC(18,2)` |
| `currency` | `String` | `USD` trong bài demo (được chuẩn hóa chữ hoa) |

Dòng `S-002,"22.00",USD` cho thấy CSV có quoting. Với dữ liệu thật, một trường có thể chứa dấu phẩy hoặc dấu nháy kép được escape; **`String.split(",")` sẽ parse sai** những trường hợp đó.

Để bài dễ xác minh, chọn tệp có đúng **3 dòng dữ liệu**, tổng tiền **35.75 USD**. Không dùng ngày hệ thống để ngầm chọn kỳ, vì một task bị khởi chạy trễ qua nửa đêm có thể vô tình nhập sai ngày.

## 7. Cấu trúc dự án Maven

Ví dụ bộ file mà người học tạo trong dự án thực hành:

~~~text
csv-import-task/
├── pom.xml
├── data/
│   └── sales-2026-11-24.csv
└── src/
    └── main/
        ├── java/com/example/csvtask/
        │   ├── CsvImportApplication.java
        │   ├── CsvFileLoader.java
        │   └── CsvImportService.java
        └── resources/
            └── application.yml
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>csv-import-task</artifactId>
    <version>1.0.0</version>
    <name>csv-import-task</name>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.2</spring-cloud.version>
        <commons-csv.version>1.14.1</commons-csv.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-task</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-csv</artifactId>
            <version>${commons-csv.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Vì sao cần từng dependency?**

- `spring-cloud-starter-task` tạo hạ tầng Task và `TaskRepository`.
- `spring-boot-starter-jdbc` cung cấp `JdbcTemplate`, `DataSource` và transaction manager.
- `postgresql` là driver kết nối database.
- `commons-csv` hỗ trợ header, field quoting và parse bản ghi.
- Không thêm Spring Batch vào bước demo chính vì **một `ApplicationRunner` đủ cho tệp nhỏ**. Phần cuối chỉ rõ cách nâng cấp sang Batch.

## 8. Cấu hình Spring Boot và TaskRepository

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: csv-import-task
  main:
    web-application-type: none
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5433/taskdemo}
    username: ${DB_USER:taskdemo}
    password: ${DB_PASSWORD:local-demo-only}
    driver-class-name: org.postgresql.Driver
  cloud:
    task:
      name: csv-import-task
      initialize-enabled: true
      closecontextEnabled: true

logging:
  level:
    org.springframework.cloud.task: INFO
~~~

Giải thích:

- `spring.main.web-application-type: none`: task chạy như console process, không khởi động HTTP server.
- `spring.datasource.*`: **PostgreSQL bền vững** được dùng bởi cả Spring Cloud Task và các bảng nghiệp vụ.
- `spring.cloud.task.name`: tên dễ truy vấn trong `TASK_EXECUTION`.
- `initialize-enabled: true`: bật khởi tạo các bảng Task theo cơ chế của phiên bản Spring Cloud Task. **Chỉ nên dùng trong bài học trên database cô lập**, sau khi kiểm tra schema có được tạo và không xung đột.
- `closecontextEnabled: true`: yêu cầu context đóng sau khi các runner hoàn tất và TaskRepository đã được cập nhật theo cơ chế framework; giúp tiến trình hữu hạn kết thúc, khi không có luồng nền giữ JVM.
- Từng lần chạy sẽ tạo **`TaskExecution` mới**, dù đầu vào và business key giống nhau.

**Production:** DBA hoặc công cụ migration phải quản lý bảng `TASK_*` đúng DDL của version, lúc đó chuyển `initialize-enabled: false` và dùng Secret cho credential. Không cấp quyền `CREATE TABLE` cho user runtime nếu không cần. Cấu hình trong bài là minh họa dành cho local; mật khẩu demo không an toàn cho hệ thống thật.

## 9. Lớp đọc và kiểm tra CSV: CsvFileLoader

Đọc tệp và validation **trước khi mở transaction** giúp transaction JDBC ngắn, không giữ lock trong lúc parse. Để hash đúng nội dung đã parse, bài học đọc một snapshot bytes duy nhất; tệp bị thay đổi sau đó không làm checksum lệch dữ liệu nhập. Giới hạn kích thước giúp ngăn dùng hết heap trong ví dụ.

Tạo `src/main/java/com/example/csvtask/CsvFileLoader.java`:

~~~java
package com.example.csvtask;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.springframework.stereotype.Component;

@Component
public class CsvFileLoader {

    private static final int MAX_BYTES = 4 * 1024 * 1024;
    private static final int MAX_ROWS = 10_000;

    public record SaleRow(
            String externalId, BigDecimal amount, String currency) {}

    public record CsvData(String sha256, List<SaleRow> rows) {}

    public CsvData load(Path file) throws IOException {
        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException(
                    "INPUT_NOT_FILE: " + file);
        }

        long fileSize = Files.size(file);
        if (fileSize == 0 || fileSize > MAX_BYTES) {
            throw new IllegalArgumentException(
                    "INPUT_SIZE_INVALID: giới hạn 4 MiB");
        }

        // Đọc đúng một snapshot bytes để parse và tính checksum.
        byte[] bytes = Files.readAllBytes(file);
        if (bytes.length == 0 || bytes.length > MAX_BYTES) {
            throw new IllegalArgumentException("INPUT_SIZE_INVALID");
        }

        // Để bài đơn giản: yêu cầu UTF-8 không BOM.
        if (bytes.length >= 3
                && (bytes[0] & 0xff) == 0xef
                && (bytes[1] & 0xff) == 0xbb
                && (bytes[2] & 0xff) == 0xbf) {
            throw new IllegalArgumentException(
                    "INPUT_BOM_NOT_SUPPORTED");
        }

        // Không âm thầm thay byte UTF-8 hỏng bằng ký tự U+FFFD.
        String csvText = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes)).toString();

        CSVFormat format = CSVFormat.RFC4180.builder()
                .setHeader()
                .setSkipHeaderRecord(true)
                .setIgnoreEmptyLines(true)
                .get();

        List<SaleRow> rows = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();

        try (CSVParser parser = CSVParser.parse(csvText, format)) {
            List<String> expected = List.of(
                    "external_id", "amount", "currency");

            if (!parser.getHeaderNames().equals(expected)) {
                throw new IllegalArgumentException(
                        "INPUT_HEADER_INVALID: " + parser.getHeaderNames());
            }

            for (CSVRecord record : parser) {
                if (!record.isConsistent()) {
                    throw new IllegalArgumentException(
                            "INVALID_COLUMNS: record=" + record.getRecordNumber());
                }
                if (rows.size() >= MAX_ROWS) {
                    throw new IllegalArgumentException(
                            "TOO_MANY_ROWS: tối đa " + MAX_ROWS);
                }

                String id = record.get("external_id").trim();
                if (!id.matches("[A-Z0-9][A-Z0-9_-]{0,63}")) {
                    throw new IllegalArgumentException(
                            "INVALID_EXTERNAL_ID: record=" + record.getRecordNumber());
                }
                if (!seenIds.add(id)) {
                    throw new IllegalArgumentException(
                            "DUPLICATE_EXTERNAL_ID: " + id);
                }

                BigDecimal amount;
                try {
                    amount = new BigDecimal(
                            record.get("amount").trim())
                            .setScale(2, RoundingMode.UNNECESSARY);
                } catch (NumberFormatException | ArithmeticException ex) {
                    throw new IllegalArgumentException(
                            "INVALID_AMOUNT: record=" + record.getRecordNumber(),
                            ex);
                }
                if (amount.signum() <= 0 || amount.precision() > 18) {
                    throw new IllegalArgumentException(
                            "INVALID_AMOUNT_RANGE: record="
                            + record.getRecordNumber());
                }

                String currency = record.get("currency")
                        .trim().toUpperCase(Locale.ROOT);
                if (!"USD".equals(currency)) {
                    throw new IllegalArgumentException(
                            "INVALID_CURRENCY: record=" + record.getRecordNumber());
                }

                rows.add(new SaleRow(id, amount, currency));
            }
        }

        if (rows.isEmpty()) {
            throw new IllegalArgumentException("EMPTY_CSV");
        }

        return new CsvData(
                sha256(bytes),
                List.copyOf(rows));
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

### 9.1. Vì sao không dùng String.split?

Định dạng CSV cho phép giá trị được bao bởi dấu nháy kép và có thể chứa dấu phẩy, dấu nháy kép escape hoặc xuống dòng trong một field. `String.split(",")` không hiểu các quy tắc đó. `CSVParser` xử lý cấu trúc bản ghi, còn ta kiểm tra **tên header và giá trị nghiệp vụ**.

### 9.2. Khi nào checksum được coi là ổn định?

`sha256(bytes)` là hash của **bytes gốc**, gồm encoding, dấu xuống dòng và khoảng trắng. Vì vậy hai tệp biểu diễn cùng dữ liệu nhưng khác CRLF/LF hoặc thêm dòng trắng có thể mang hash khác và bị xem là **khác nội dung**. Đây là **chính sách strict-bytes** có chủ đích cho ví dụ.

Nếu hệ thống muốn so sánh tương đương **theo bản ghi nghiệp vụ**, cần định nghĩa quá trình canonicalization có version trước khi băm. Không đổi chính sách hash âm thầm sau khi dữ liệu đã được nhập.

### 9.3. Giới hạn demo

- Toàn bộ tệp nhỏ được đọc vào `byte[]`/`String`, rồi danh sách dòng vào bộ nhớ; không dùng cách này cho CSV hàng GiB.
- Chỉ hỗ trợ `USD` để tránh phải xử lý tiền đa loại và quy tắc làm tròn khác nhau.
- Parser từ chối UTF-8 có BOM; muốn hỗ trợ phải bỏ BOM **đúng cách** và quy định bytes nào được hash.
- Nếu file đang được ghi đồng thời, snapshot có thể chứa nội dung chưa hoàn chỉnh. Nên đưa vào hệ thống qua **file tạm → atomic rename** hoặc object storage có version/ETag.

## 10. Service ghi PostgreSQL trong một transaction

Tạo `src/main/java/com/example/csvtask/CsvImportService.java`:

~~~java
package com.example.csvtask;

import java.sql.Date;
import java.time.LocalDate;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.example.csvtask.CsvFileLoader.CsvData;
import com.example.csvtask.CsvFileLoader.SaleRow;

@Service
public class CsvImportService {

    private final JdbcTemplate jdbc;

    public CsvImportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record ImportRequest(
            String tenant, LocalDate businessDate, String sourceVersion) {}

    public enum Outcome {
        CREATED, ALREADY_APPLIED
    }

    private record Existing(String sha256, int rows) {}

    @Transactional
    public Outcome importOnce(
            ImportRequest request,
            CsvData data,
            boolean failAfterFirstRow) {

        Date date = Date.valueOf(request.businessDate());

        // Ledger và tất cả sales_line thuộc CÙNG transaction.
        int inserted = jdbc.update("""
            INSERT INTO csv_import (
                tenant_id, business_date, source_version,
                input_sha256, row_count
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, business_date, source_version)
            DO NOTHING
            """,
            request.tenant(), date, request.sourceVersion(),
            data.sha256(), data.rows().size());

        if (inserted == 0) {
            // Khi đã có business key, KHÔNG INSERT thêm rows.
            Existing existing = jdbc.queryForObject("""
                SELECT input_sha256, row_count
                FROM csv_import
                WHERE tenant_id = ?
                  AND business_date = ?
                  AND source_version = ?
                """,
                (rs, i) -> new Existing(
                        rs.getString("input_sha256").trim(),
                        rs.getInt("row_count")),
                request.tenant(), date, request.sourceVersion());

            if (!existing.sha256().equals(data.sha256())
                    || existing.rows() != data.rows().size()) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_CONFLICT: key đã gắn tệp khác");
            }

            Long actualRows = jdbc.queryForObject("""
                SELECT COUNT(*)
                FROM sales_line
                WHERE tenant_id = ?
                  AND business_date = ?
                  AND source_version = ?
                """,
                Long.class,
                request.tenant(), date, request.sourceVersion());

            if (actualRows == null
                    || actualRows.longValue() != data.rows().size()) {
                throw new IllegalStateException(
                        "INTEGRITY_MISMATCH: ledger khác dữ liệu");
            }

            return Outcome.ALREADY_APPLIED;
        }

        int rowNumber = 0;
        for (SaleRow row : data.rows()) {
            jdbc.update("""
                INSERT INTO sales_line (
                    tenant_id, business_date, source_version,
                    external_id, amount, currency
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                request.tenant(), date, request.sourceVersion(),
                row.externalId(), row.amount(), row.currency());

            rowNumber++;
            if (failAfterFirstRow && rowNumber == 1) {
                throw new IllegalStateException(
                        "DEMO_FAILURE_BEFORE_COMMIT");
            }
        }

        return Outcome.CREATED;
    }
}
~~~

### 10.1. Vì sao transaction bao cả hai bảng?

Khi `@Transactional` chạy đúng qua Spring bean proxy, cùng `DataSourceTransactionManager` bao các câu lệnh SQL. Nếu một dòng gây exception trước commit, PostgreSQL rollback **cả ledger và những dòng đã insert trước đó**.

Đừng tách:

~~~text
transaction A: INSERT csv_import, COMMIT
transaction B: INSERT từng sales_line, COMMIT
~~~

vì JVM có thể chết sau transaction A, để lại ledger báo đã nhập nhưng dữ liệu chưa đủ.

**Trong ví dụ, không có API ngoài database hoặc file output được ghi bên trong transaction**; nếu có, rollback JDBC không thể tự hoàn tác các tác động ấy. Với hệ thống nhiều bước, cần checkpoint/outbox/idempotency tại nơi tác động.

### 10.2. Vì sao cần khóa chính ngay cả khi đã SELECT?

Hai tiến trình khởi chạy cùng kỳ có thể đồng thời `SELECT` thấy "chưa có". Nếu chỉ kiểm tra rồi ghi, cả hai có thể tạo dữ liệu. `PRIMARY KEY` và `ON CONFLICT DO NOTHING` đặt tuyến phòng vệ ở PostgreSQL, giúp trường hợp cạnh tranh được giải quyết nguyên tử. Ví dụ giả định PostgreSQL ở mức cô lập mặc định **READ COMMITTED**.

Khi một transaction giữ khóa unique chưa commit, transaction khác có thể phải chờ kết quả; không nên suy diễn từ log "INSERT đang chờ" rằng đã có lỗi. Với isolation khác, cần xem xét lỗi serialization và retry **toàn transaction**.

### 10.3. Trạng thái commit không rõ

Giả sử PostgreSQL đã nhận `COMMIT` nhưng mạng đứt trước phản hồi. Caller có thể nhận lỗi kết nối và Task báo failed, **dù dữ liệu đã được lưu**. Lần chạy sau dùng **cùng business key và cùng bytes**, sẽ:

- Phát hiện ledger hiện có.
- So sánh SHA-256, số dòng và số record đã commit.
- Trả `ALREADY_APPLIED` mà không tạo dữ liệu thứ hai.

Khi DB chưa thể kết nối, **không thể kết luận** transaction trước đã rollback. Bộ điều phối phải giữ trạng thái cần đối soát rồi thử đọc lại sau, thay vì launch vô hạn.

### 10.4. Hiệu năng

Ở tệp 3 dòng, gọi `jdbc.update` từng dòng dễ hiểu. Với vài nghìn dòng, có thể dùng `JdbcTemplate.batchUpdate` để giảm round-trip nhưng vẫn giữ trong **một transaction**. Với tệp rất lớn, việc gom hết vào một transaction tạo lock lâu, dữ liệu rollback lớn và nhiều bộ nhớ; đó là lúc cần mô hình chunk của Spring Batch.

## 11. ApplicationRunner: nhận tham số và gọi service

Tạo `src/main/java/com/example/csvtask/CsvImportApplication.java`:

~~~java
package com.example.csvtask;

import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import com.example.csvtask.CsvImportService.ImportRequest;
import com.example.csvtask.CsvImportService.Outcome;

@SpringBootApplication
public class CsvImportApplication {

    private static final Logger log =
            LoggerFactory.getLogger(CsvImportApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(CsvImportApplication.class, args);
    }

    @Bean
    ApplicationRunner importRunner(
            CsvFileLoader loader, CsvImportService service) {
        return args -> {
            String tenant = required(args, "tenant");
            String sourceVersion = required(args, "sourceVersion");
            LocalDate businessDate =
                    LocalDate.parse(required(args, "businessDate"));
            String runId = required(args, "runId");
            Path file = Path.of(required(args, "input"));

            if (!tenant.matches("[a-z0-9][a-z0-9-]{0,63}")) {
                throw new IllegalArgumentException("INVALID_TENANT");
            }
            if (!sourceVersion.matches(
                    "[A-Za-z0-9][A-Za-z0-9_-]{0,31}")) {
                throw new IllegalArgumentException("INVALID_SOURCE_VERSION");
            }

            log.info(
                    "event=csv.import.start runId={} tenant={} date={} version={}",
                    runId, tenant, businessDate, sourceVersion);

            CsvFileLoader.CsvData data = loader.load(file);
            ImportRequest request = new ImportRequest(
                    tenant, businessDate, sourceVersion);

            // Chỉ dùng cờ này trong môi trường test để chứng minh rollback.
            boolean failDemo = args.containsOption("failAfterFirstRow");

            Outcome outcome = service.importOnce(
                    request, data, failDemo);

            // Lệnh này chạy sau khi proxy @Transactional commit thành công.
            log.info(
                    "event=csv.import.done runId={} outcome={} rows={} sha256={}",
                    runId, outcome, data.rows().size(), data.sha256());
        };
    }

    private static String required(
            ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);
        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Cần truyền đúng một --" + name + "=...");
        }
        return values.get(0).trim();
    }
}
~~~

**Quan sát luồng gọi:**

1. `SpringApplication.run` tạo context, thiết lập `DataSource` và lifecycle Spring Cloud Task.
2. `ApplicationRunner` nhận tham số, parse tệp và validate.
3. Gọi `service.importOnce(...)` **qua bean Spring**, để `@Transactional` được áp dụng.
4. Service trả `CREATED` hoặc `ALREADY_APPLIED` sau khi transaction đã commit thành công từ góc nhìn caller.
5. Spring Cloud Task ghi nhận kết thúc vào `TaskRepository` khi hạ tầng còn hoạt động.

Nếu parser/service ném exception, runner **không nuốt lỗi**. Spring Boot/Task sẽ xử lý lỗi theo cơ chế vòng đời; mã thoát và metadata được quan sát ở các bước kiểm chứng. `runId` phục vụ nối log giữa scheduler và ứng dụng, **không** là khóa chống trùng nghiệp vụ.

### Vì sao không gọi System.exit ngay trong runner?

Gọi `System.exit(...)` trước khi vòng đời Spring Cloud Task kết thúc có thể ngăn việc ghi `END_TIME`/`EXIT_CODE` và đóng tài nguyên bình thường. Trong ví dụ, để Spring Boot/Task điều phối vòng đời; với môi trường cần thoát tường minh, chỉ áp dụng chính sách exit sau khi context/lifecycle đã hoàn tất và kiểm tra version.

## 12. Đóng gói và chạy import lần đầu

Từ thư mục dự án thực hành:

~~~bash
./mvnw clean package
~~~

Nếu dự án dùng Maven cài sẵn, có thể thay bằng `mvn clean package`; trên Windows, dùng `mvnw.cmd clean package`. Artifact ví dụ:

~~~text
target/csv-import-task-1.0.0.jar
~~~

Chạy với đường dẫn input tương đối tới thư mục làm việc hiện tại:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-24 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-001
~~~

Kỳ vọng log nghiệp vụ có thông điệp tương tự:

~~~text
event=csv.import.start runId=demo-001 tenant=shop-01 date=2026-11-24 version=v1
event=csv.import.done runId=demo-001 outcome=CREATED rows=3 sha256=<hash 64 ký tự>
~~~

Số `TASK_EXECUTION_ID` và hash cụ thể do framework và bytes của file quyết định. Chỉ thấy log `outcome=CREATED` chưa chứng minh TaskRepository đã cập nhật metadata cuối; bước kiểm tra SQL tiếp theo mới xác nhận.

## 13. Truy vấn PostgreSQL để xác minh nghiệp vụ

Trong `psql` hoặc SQL client, chạy:

~~~sql
SELECT tenant_id, business_date, source_version,
       row_count, input_sha256, completed_at
FROM csv_import
ORDER BY completed_at DESC;
~~~

Dự kiến một ledger cho `shop-01, 2026-11-24, v1` với `row_count=3`.

~~~sql
SELECT external_id, amount, currency
FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1'
ORDER BY external_id;
~~~

Kỳ vọng:

| external_id | amount | currency |
| --- | ---: | --- |
| S-001 | 10.50 | USD |
| S-002 | 22.00 | USD |
| S-003 | 3.25 | USD |

Tổng hợp:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';
~~~

Kỳ vọng:

~~~text
row_count   | total_amount
3           | 35.75
~~~

**Bất biến quan trọng:** dữ liệu nghiệp vụ được xác định bằng **business key**, không bằng `TASK_EXECUTION_ID` vì mỗi lần thử có thể có Task ID mới.

## 14. Truy vấn lịch sử Spring Cloud Task bền vững

Nếu hạ tầng Task khởi tạo bảng thành công, kiểm tra:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE,
       EXIT_MESSAGE,
       ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'csv-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Các trường cần hiểu:

| Trường | Ý nghĩa |
| --- | --- |
| `TASK_EXECUTION_ID` | ID duy nhất của **mỗi lần chạy ứng dụng** |
| `TASK_NAME` | Tên Task từ cấu hình |
| `START_TIME` | Khi framework ghi nhận bắt đầu |
| `END_TIME` | Khi framework ghi nhận kết thúc, nếu ghi được |
| `EXIT_CODE` | Mã kết quả theo cơ chế Spring Boot/Spring Cloud Task |
| `EXIT_MESSAGE` | Thông điệp hoàn tất nếu ứng dụng/listener có thiết lập |
| `ERROR_MESSAGE` | Có thể chứa phần dấu vết exception khi xảy ra lỗi mà Task quan sát được |

Ứng dụng demo **không chủ động đặt `EXIT_MESSAGE`**, nên trường này có thể để trống. Đừng đòi chuỗi `CREATED` hay `ALREADY_APPLIED` phải tự xuất hiện trong `EXIT_MESSAGE`: hai giá trị ấy hiện được ghi trong log của runner.

### Một vài kết quả cần đọc đúng

- Run thành công bình thường: kỳ vọng có `END_TIME` và `EXIT_CODE=0` theo chính sách framework.
- Runner ném exception: kỳ vọng mã thất bại, và có thể có `ERROR_MESSAGE`; nội dung cụ thể tùy version/giới hạn cột.
- Nếu JVM bị kill, mất DB hoặc lỗi bootstrap rất sớm: record có thể **thiếu `END_TIME` hoặc không tồn tại**.
- Có nhiều `TASK_EXECUTION` cùng `TASK_NAME` là bình thường khi đã thử lại; kiểm tra dữ liệu nghiệp vụ để xác định có trùng hay không.

### Tại sao lịch sử tồn tại sau JVM exit?

Vì `spring.datasource` trỏ tới **PostgreSQL** với volume bền vững thay vì một repository Map trong bộ nhớ JVM hay H2 `mem:`. Lịch sử được lưu vào database, không nằm trong bean của tiến trình đã kết thúc.

Tuy nhiên, **database bền vững không phải bản sao lưu**. Volume có thể bị xóa, ổ đĩa hỏng hoặc database mất dữ liệu; production cần backup, kiểm tra phục hồi, retention, kiểm soát truy cập và migration schema.

## 15. Nhập lại cùng tệp và kiểm chứng idempotency

Chạy lần thứ hai, **giữ nguyên tenant/date/version/input**, đổi chỉ `runId`:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-24 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-002
~~~

Log dự kiến:

~~~text
event=csv.import.done runId=demo-002 outcome=ALREADY_APPLIED rows=3 sha256=<cùng hash>
~~~

Kiểm chứng:

~~~sql
SELECT COUNT(*) FROM sales_line
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';

SELECT COUNT(*) FROM csv_import
WHERE tenant_id = 'shop-01'
  AND business_date = DATE '2026-11-24'
  AND source_version = 'v1';
~~~

Kỳ vọng lần lượt **3** và **1**. Trong khi đó:

~~~sql
SELECT TASK_EXECUTION_ID, START_TIME, END_TIME, EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'csv-import-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

sẽ có thêm **một lần thực thi mới** nếu TaskRepository ghi nhận thành công. Đây là kết quả đúng: **nhiều attempt, một hiệu ứng nghiệp vụ**.

### Cùng khóa nhưng file khác

Tạo bản sao CSV và thay `S-003,3.25,USD` thành `S-003,99.00,USD`, rồi thử chạy cùng `tenant`, `businessDate`, `sourceVersion`. Hash khác và service phải báo:

~~~text
IDEMPOTENCY_CONFLICT: key đã gắn tệp khác
~~~

Dữ liệu đã nhập trước **không thay đổi**. Nếu thực sự muốn tạo bản báo cáo/nhập dữ liệu mới, hãy quyết định **phiên bản nghiệp vụ mới** (ví dụ `--sourceVersion=v2`) theo quy tắc hệ thống, không âm thầm sửa lịch sử của `v1`.

## 16. Thử lỗi validation trước transaction

Sửa một bản sao tệp, ví dụ:

~~~csv
external_id,amount,currency
S-101,10.50,USD
S-102,not-a-number,USD
~~~

Chạy với **businessDate khác** để không đụng dữ liệu đã thành công:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-25 --sourceVersion=v1 --input=data/invalid-sales.csv --runId=demo-invalid
~~~

Kỳ vọng:

- Parser ném `INVALID_AMOUNT`.
- Không có dòng cho kỳ `2026-11-25` trong `csv_import` hoặc `sales_line`.
- Spring Boot/Task phản ánh lỗi của runner nếu context và repository hoạt động đủ; tra `EXIT_CODE` và `ERROR_MESSAGE`.
- Scheduler hoặc shell quan sát **process thất bại**, không gọi thành công chỉ vì JDBC không ghi dữ liệu.

Dùng SQL:

~~~sql
SELECT COUNT(*) FROM csv_import
WHERE business_date = DATE '2026-11-25';

SELECT COUNT(*) FROM sales_line
WHERE business_date = DATE '2026-11-25';
~~~

Cả hai dự kiến bằng `0` trên database test này. Thay vì parse bằng `split(",")` rồi tự bắt lỗi, hãy giữ parser/validation tách biệt để có mã lỗi rõ ràng và không giữ connection/transaction trong lúc đọc tệp.

## 17. Thử rollback khi lỗi xảy ra giữa transaction

Để chứng minh transaction thực sự bảo vệ **cả hai bảng**, chạy cùng tệp hợp lệ với business key **chưa từng nhập** và cờ `--failAfterFirstRow`:

~~~bash
java -jar target/csv-import-task-1.0.0.jar --tenant=shop-01 --businessDate=2026-11-26 --sourceVersion=v1 --input=data/sales-2026-11-24.csv --runId=demo-rollback --failAfterFirstRow
~~~

Theo mã ở mục 10, thứ tự logic là:

1. Insert một ledger `csv_import`.
2. Insert dòng `S-001` vào `sales_line`.
3. Ném `DEMO_FAILURE_BEFORE_COMMIT`.
4. Spring transaction interceptor đánh dấu rollback và PostgreSQL rollback cả hai thay đổi.

Truy vấn:

~~~sql
SELECT COUNT(*) FROM csv_import
WHERE business_date = DATE '2026-11-26';

SELECT COUNT(*) FROM sales_line
WHERE business_date = DATE '2026-11-26';
~~~

Kỳ vọng **0** và **0**. Nếu ledger còn mà rows không có, cần kiểm tra `@Transactional` có thực sự chạy qua bean proxy không, có dùng chung `DataSource`/transaction manager không và có đoạn mã nào tự commit ngoài transaction không.

Sau khi bỏ cờ `--failAfterFirstRow` và dùng lại đúng business key, chương trình phải tạo đủ 3 dòng (`CREATED`). Việc này khác với timeout **sau commit**; lúc đó kết quả có thể đã có và lần sau trả `ALREADY_APPLIED`.

### Chú ý về phép thử

Đây là thử **exception trước commit**, không tự mô phỏng được chính xác lỗi mạng **ngay sau PostgreSQL đã commit nhưng trước khi client nhận ACK**. Với trường hợp commit không rõ, cần fault injection ở mức kết nối/driver hoặc mô phỏng caller nhận exception sau khi service đã commit, rồi kiểm tra rằng lần chạy lại không sinh bản trùng.

## 18. Kiểm tra tính bền vững khi JVM và PostgreSQL được restart

Đầu tiên, kết thúc mọi tiến trình `java -jar`. Trong `psql`, ghi lại số lượng ledger, sales và TaskExecution.

Sau đó dừng và khởi động lại PostgreSQL **mà không xóa volume**:

~~~bash
docker stop csv-task-postgres
docker start csv-task-postgres
docker exec csv-task-postgres pg_isready -U taskdemo -d taskdemo
~~~

Kết nối lại:

~~~bash
docker exec -it csv-task-postgres psql -U taskdemo -d taskdemo
~~~

Kiểm tra:

~~~sql
SELECT COUNT(*) FROM csv_import;
SELECT COUNT(*) FROM sales_line;
SELECT COUNT(*) FROM TASK_EXECUTION;
~~~

Số đếm phải giữ nguyên so với trước khi dừng container nếu không có tiến trình khác thêm dữ liệu và volume được giữ đúng. Sau khi khởi động lại JAR, nhập cùng key `2026-11-24/v1` phải trả `ALREADY_APPLIED` và tạo thêm một TaskExecution; đây chính là sự khác biệt giữa **metadata JDBC bền vững** với kho trong bộ nhớ chỉ sống theo JVM.

Nếu muốn thực sự thử failover/backups production, cần **backup/restore** và diễn tập phục hồi trên DB mới, không chỉ stop/start container.

## 19. Kiểm thử hai tiến trình chạy đồng thời

`TaskRepository` chỉ theo dõi từng TaskExecution; nó không thay thế cơ chế chống trùng ở database. Một thử nghiệm bổ sung:

1. Chuẩn bị business key mới, ví dụ `shop-01|2026-11-27|v1`.
2. Khởi chạy **hai tiến trình** `java -jar` cùng key và cùng CSV gần như đồng thời.
3. Đợi cả hai kết thúc.
4. Truy vấn bảng `csv_import` và `sales_line` cho kỳ đó.

Kỳ vọng:

- Đúng **1 ledger** và **3 sales_line**.
- Một tiến trình có thể trả `CREATED`; tiến trình còn lại sau khi xung đột unique được xử lý sẽ trả `ALREADY_APPLIED`.
- `TASK_EXECUTION` có thể lưu **2 lần chạy**.
- PostgreSQL có thể khiến một transaction chờ transaction khác giải quyết unique key; không phải race condition nào cũng xuất hiện trong log.

Ràng buộc chính ở PostgreSQL phải tồn tại trước khi chạy test. Đừng dùng cả hai tiến trình cùng `--failAfterFirstRow` để suy ra hành vi thành công. Trong production, cần thêm giới hạn concurrency, timeout và kiểm soát retry ở scheduler, vì khóa duy nhất **không giải quyết việc hai tác vụ cùng tiêu thụ CPU/IO quá mức**.

## 20. Khi TaskRepository không có record hoàn tất

Một phần quan trọng của bài là biết **giới hạn quan sát**:

| Tình huống | Dữ liệu nghiệp vụ | Metadata `TASK_EXECUTION` | Cần làm |
| --- | --- | --- | --- |
| Thành công bình thường | Đã commit | Thường có `END_TIME`, `EXIT_CODE=0` | Đối chiếu output |
| CSV sai trước transaction | Không có kết quả mới | Có thể ghi lỗi của runner | Xem log và `ERROR_MESSAGE` |
| Exception trong transaction | Rollback | Có thể ghi thất bại | Kiểm chứng bằng SQL |
| Mạng đứt đúng quanh commit | **Không xác định** đến khi đối soát | Có thể thiếu/có mã lỗi | Đọc bảng nghiệp vụ theo key |
| JVM bị `SIGKILL` sau commit | Có thể đã đủ kết quả | Có thể thiếu `END_TIME` | Đối soát DB + trạng thái process |
| `ApplicationContext` lỗi trước khi Task sẵn sàng | Chưa thực hiện runner | **Có thể không có record** | Xem log bootstrap/scheduler |
| Database không truy cập được khi startup | Task không ghi được metadata | Có thể không tạo record | Kiểm tra DB và hạ tầng |

**Kết luận:** `END_TIME IS NULL` không đồng nghĩa task còn chạy; không có TaskExecution cũng không chứng minh JVM chưa từng được khởi động. Cần kết hợp scheduler/container, log, metadata và **kết quả nghiệp vụ đã commit**.

## 21. Khác biệt giữa TaskRepository và bảng ledger

Dễ nhầm giữa `TaskRepository` và bảng `csv_import` vì cả hai đều liên quan đến "lịch sử":

- `TaskRepository`: lịch sử **nhiều lần chạy kỹ thuật**. Nó giúp kiểm tra lúc nào, exit code nào, vì sao runner lỗi.
- `csv_import`: lịch sử **nhập nghiệp vụ đã hoàn thành** cho một business key. Nó giúp quyết định có được ghi lại hay không.

Ví dụ ba lần thử:

| Lần thử | Task exit code | Ledger theo cùng key | Sales lines |
| --- | --- | ---: | ---: |
| 1 — lỗi trước commit | Khác 0 theo policy | 0 | 0 |
| 2 — nhập thành công | 0 | 1 | 3 |
| 3 — nhập lại cùng bytes | 0 | 1 | 3 |

Đừng xóa TaskExecution của lần thử lỗi để "làm đẹp" báo cáo. Và đừng dùng `TASK_EXECUTION_ID` làm khóa unique cho sales data: nó sẽ thay đổi ở mỗi retry, khiến việc nhập trùng không bị phát hiện.

## 22. Nếu muốn làm bằng Spring Batch

Với dữ liệu lớn hoặc cần restart từ checkpoint, có thể thay `ApplicationRunner` bằng **Spring Batch Job** (vẫn chạy trong ứng dụng Spring Cloud Task):

~~~mermaid
flowchart LR
    A["FlatFileItemReader<SaleRow>"] --> B["ItemProcessor: validation"]
    B --> C["JdbcBatchItemWriter: PostgreSQL"]
    C --> D["JobRepository: checkpoint/StepExecution"]
    E["Spring Cloud Task"] --> F["TaskRepository: TaskExecution"]
    D --> G["Đối soát theo business key"]
    F --> G
~~~

Một Job thường có:

- `FlatFileItemReader` đọc CSV theo chunk; cấu hình `LineMapper`/`FieldSetMapper` đúng schema.
- `ItemProcessor` kiểm tra mã giao dịch, tiền, checksum hoặc chuẩn hóa.
- `JdbcBatchItemWriter` ghi kết quả, tham gia transaction chunk khi cấu hình đúng.
- `JobRepository` lưu `JobExecution`, `StepExecution` và `ExecutionContext` để hỗ trợ restart.
- `TaskRepository` lưu **một lần chạy ứng dụng**, độc lập với checkpoint từng Step.

Khi kết hợp, cần kiểm tra `BatchStatus.FAILED` có được phản ánh lên mã thoát Task. Với phiên bản hỗ trợ có thể dùng `spring.cloud.task.batch.fail-on-job-failure=true`. Không tự suy ra rằng Spring Batch bảo đảm đúng một lần với API ngoài database, file output hoặc message broker.

**Cảnh báo restart:** một Batch Job có nhiều chunk có thể đã commit các chunk trước khi bị dừng. Retry cả process với `JobParameters` khác có thể tạo `JobInstance` mới và làm lại dữ liệu. Dù có checkpoint, **unique business key và idempotency tại nơi ghi** vẫn cần thiết.

## 23. Khi triển khai theo lịch hoặc bằng API

Một scheduler có thể chạy JAR mỗi ngày với các tham số:

~~~text
--tenant=shop-01
--businessDate=2026-11-24
--sourceVersion=v1
--input=/data/imports/sales-2026-11-24.csv
--runId=schedule-20261124-attempt1
~~~

**Bắt buộc cố định businessDate theo occurrence thực sự**, không gọi `LocalDate.now()` trong runner rồi vô tình chọn sai kỳ khi lịch đến trễ. `runId` có thể khác giữa các attempt nhưng `tenant/businessDate/sourceVersion` phải giữ nguyên với cùng yêu cầu.

Nếu dùng Kubernetes CronJob hay Spring Cloud Data Flow:

1. **Định danh request** trước khi launch và ghi receipt.
2. **Chống chạy chồng** bằng scheduler policy phù hợp; ràng buộc unique DB vẫn là điểm chặn cuối cùng.
3. **Kiểm tra completion** qua TaskExecution và process exit code; không coi launch ACK là thành công.
4. **Đối soát output** trước khi tự động retry sau timeout hoặc lỗi commit không rõ.
5. **Giới hạn số lần retry** và thời gian chạy để tránh bùng nổ request.
6. Truyền tệp qua volume/object storage được kiểm soát, không phụ thuộc path ngẫu nhiên của pod.
7. Lưu log tập trung bằng `runId`, không ghi secret hoặc toàn bộ nội dung CSV nhạy cảm.

## 24. Những lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Connection refused` | PostgreSQL chưa chạy, sai host/port | `pg_isready`, port mapping, `DB_URL` |
| `relation "task_execution" does not exist` | Schema Task chưa được tạo, sai schema/prefix | Initializer, migration, `search_path` |
| `permission denied for table` | JDBC user thiếu quyền | Quyền SELECT/INSERT/UPDATE, migration riêng |
| `INPUT_HEADER_INVALID` | Sai header, BOM hoặc đổi tên/case | Kiểm tra UTF-8, ba cột chuẩn |
| `INVALID_AMOUNT` | Số có dấu phẩy thập phân, chữ hoặc quá hai số lẻ | Dùng dấu chấm và `BigDecimal` theo contract |
| `DUPLICATE_EXTERNAL_ID` | CSV có hai dòng cùng mã | Sửa file nguồn; không tự xóa một dòng im lặng |
| `IDEMPOTENCY_CONFLICT` | Cùng kỳ/version nhưng file đã thay đổi | Đối soát; dùng version mới nếu hợp lệ |
| `ALREADY_APPLIED` nhưng chưa thấy row mới | Đây là kết quả chạy lại cùng yêu cầu | Kiểm tra ledger và các row đã commit |
| Ledger còn mà sales thiếu | Schema/transaction khác, chỉnh tay DB hoặc lỗi thiết kế | Kiểm tra transaction và `INTEGRITY_MISMATCH` |
| `END_TIME IS NULL` | JVM còn chạy hoặc lỗi trước cập nhật cuối | Xem runtime/log/DB, không tự suy diễn |
| Chạy lần hai lại bị tạo schema lỗi | Cơ chế initializer/version/schema không khớp | Chuyển sang migration chuẩn, `initialize-enabled: false` |
| Dữ liệu mất sau container bị xóa | Volume không được giữ hoặc dùng DB khác | Kiểm tra volume, JDBC URL, backup |
| Task exit khác 0 nhưng sales đã có | Lỗi xảy ra sau commit | Đối soát key/hash trước khi retry |

## 25. Checklist vận hành an toàn

- [ ] Có version Java/Spring Boot/Spring Cloud Task tương thích và cấu hình Maven tái lập.
- [ ] PostgreSQL dùng storage bền vững; production có backup/restore đã kiểm thử.
- [ ] Schema `TASK_*` được quản lý theo đúng version framework, không tự tạo từ suy đoán.
- [ ] Business key và version của kỳ nhập được xác định trước khi chạy.
- [ ] CSV được xác minh encoding, header, số cột, kiểu dữ liệu, giới hạn kích thước và ID trùng.
- [ ] Cả ledger và rows được ghi **trong một transaction**.
- [ ] Có `PRIMARY KEY`/`UNIQUE` chống chạy trùng giữa các process.
- [ ] Cùng key + cùng checksum → không ghi trùng; cùng key + checksum khác → conflict.
- [ ] Khi mất kết nối lúc commit, có quy trình đối soát; không tự coi đã rollback.
- [ ] Khi failure, runner không nuốt exception khiến scheduler báo thành công giả.
- [ ] Đã thử rollback, nhập lại, restart PostgreSQL và hai process song song.
- [ ] Log có `runId`, giới hạn độ dài và không lộ password/PII.
- [ ] Scheduler có deadline, retry budget và xử lý kỳ bị bỏ lỡ.
- [ ] Nếu tệp lớn, chuyển sang Spring Batch chunk processing hoặc streaming có checkpoint/idempotency.

## 26. Bài tập nâng cao

**Bài tập A — Đổi tên tệp nhưng giữ nội dung.** Sao chép CSV sang một đường dẫn khác, chạy cùng business key và kiểm tra hash. Giải thích vì sao lần thứ hai phải trả `ALREADY_APPLIED`.

**Bài tập B — Chỉnh nội dung.** Thêm một dòng `S-004,5.00,USD` vào CSV nhưng giữ nguyên `sourceVersion=v1`. Vì sao không nên tự động ghi thêm dòng đó vào import đã hoàn tất?

**Bài tập C — Chống trùng đồng thời.** Mở hai terminal và chạy cùng một key mới. Xác minh một ledger, ba sales và hai TaskExecution khi mọi thứ hoạt động bình thường.

**Bài tập D — Lỗi khi ghi.** Chạy với `--failAfterFirstRow`. Giải thích lý do cả ledger lẫn sales đều rollback khi `@Transactional` hiệu lực.

**Bài tập E — Metadata sau crash.** Trong môi trường thử nghiệm, chủ động kill một process sau khi DB commit nhưng trước khi TaskRepository cập nhật cuối. Đối chiếu exit code, `END_TIME`, ledger và sales. Viết kế hoạch xác minh trước retry.

**Bài tập F — Batch.** Thay parser và vòng insert bằng `FlatFileItemReader`, `ItemProcessor`, `JdbcBatchItemWriter` và `JobRepository`. Kiểm tra restart sau khi một chunk đã commit mà chunk sau thất bại.

**Bài tập G — Đổi checksum policy.** Thiết kế canonicalization độc lập với CRLF/LF, công bố `hashVersion` và thử hai tệp có bytes khác nhưng bản ghi tương đương. Giải thích vì sao không được thay logic hash mà không versioning dữ liệu cũ.

## 27. Tự kiểm tra kiến thức

**Câu 1.** Vì sao dữ liệu trong `TASK_EXECUTION` có thể có ba row dù bảng `csv_import` chỉ có một ledger?

**Câu 2.** Khi file CSV thay đổi nhưng `tenant`, `businessDate` và `sourceVersion` không đổi, hệ thống phải làm gì? Vì sao không overwrite tự động?

**Câu 3.** Lỗi `SQLException` ở thời điểm `COMMIT` có chứng minh PostgreSQL đã rollback không?

**Câu 4.** Vì sao chọn `jdbc:postgresql://...` với volume bền vững quan trọng cho lịch sử giữa nhiều lần chạy hơn là Map repository trong JVM?

**Câu 5.** `@Transactional` đặt trên service có được áp dụng nếu method được gọi trực tiếp từ một method khác cùng class (self-invocation) không?

**Câu 6.** Đọc CSV bằng `String.split(",")` khác gì thư viện CSV có hỗ trợ quoting và header?

**Câu 7.** Nếu muốn xử lý tệp 10 triệu dòng, bạn sẽ thay đổi kiến trúc và chiến lược restart như thế nào?

## 28. Ghi nhớ

- **Spring Cloud Task** quản lý metadata của một lần chạy hữu hạn; **PostgreSQL TaskRepository** giữ lịch sử sau khi JVM thoát.
- **CSV ingestion** cần kiểm tra format/encoding/schema và dữ liệu nghiệp vụ; không nên parse bằng `split(",")`.
- `@Transactional` cùng ràng buộc `PRIMARY KEY` giúp ledger và sales rows được commit nguyên tử, bảo vệ chống dữ liệu dở khi lỗi trước commit.
- **Idempotency key** là `tenant + businessDate + sourceVersion`; hash của bytes cho biết lần chạy lại có đúng cùng file hay không.
- Một Task có thể chạy nhiều lần nhưng chỉ nên tạo **một kết quả cho cùng business key**; `TASK_EXECUTION_ID` không phải khóa chống trùng nghiệp vụ.
- **Lỗi mạng quanh `COMMIT` tạo trạng thái chưa xác định**, phải đối soát bằng dữ liệu đã commit trước khi retry.
- `END_TIME IS NULL` hoặc không có TaskExecution không chứng minh công việc chưa chạy, vì lỗi bootstrap, JVM kill và DB failure có thể làm mất metadata.
- Với dữ liệu rất lớn, dùng Spring Batch hoặc kiến trúc streaming/chunk; vẫn cần tính idempotent ở nơi ghi.

## Tài liệu tham khảo

- [Spring Cloud Task Reference — Features và Task Lifecycle](https://docs.spring.io/spring-cloud-task/reference/features.html): cách tạo/cập nhật `TaskExecution`, `TaskRepository` và giới hạn ghi nhận lỗi khởi động.
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html): `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS` và các bảng khác.
- [Spring Cloud Task — TaskRepositoryInitializer API](https://docs.spring.io/spring-cloud-task/docs/current/apidocs/org/springframework/cloud/task/repository/support/TaskRepositoryInitializer.html): khởi tạo bảng Task khi có `DataSource` và `initialize-enabled`.
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/): ghép phiên bản Spring Cloud và Spring Boot.
- [Spring Cloud 2025.0.2 Release Announcement](https://spring.io/blog/2026/04/02/spring-cloud-2025-0-2-aka-northfields-has-been-released/): baseline Spring Boot 3.5.13.
- [Apache Commons CSV — User Guide và API](https://commons.apache.org/proper/commons-csv/): parser RFC 4180, header, quoting, record consistency.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): hành vi `ON CONFLICT DO NOTHING`.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): tính nhất quán và concurrent transaction.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxy và rollback.
- [Spring Batch — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): phương án nâng cấp khi dữ liệu lớn.

**Lưu ý:** Các đường dẫn JAR, tên database, mật khẩu và giá trị đầu vào trong bài là minh họa. Đây là tài liệu hướng dẫn tự dựng và chạy dự án, **không phải lời khẳng định đã compile/test code trong workspace**. Trước khi dùng thực tế, cần kiểm tra phiên bản, DDL, quyền PostgreSQL, giới hạn dữ liệu và chạy bộ kiểm thử tích hợp riêng. Vòng Content QA theo quy trình nội dung sẽ thực hiện sau giai đoạn viết bài.
