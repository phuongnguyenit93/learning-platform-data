# Thực hành thiết kế sổ giao dịch trên Spanner

Một ví điện tử Java cần chuyển 25,00 USD từ tài khoản A sang B. Nếu ứng dụng trừ tiền A thành công nhưng cộng tiền B thất bại, dữ liệu sẽ sai. Nếu client gửi lại cùng request sau timeout, hệ thống có thể chuyển tiền **hai lần**. Bài thực hành này dùng **Google Cloud Spanner** để xây một *sổ giao dịch kép đơn giản* (double-entry ledger): mỗi lần chuyển tiền tạo hai dòng biến động bằng nhau và trái dấu, đồng thời cập nhật số dư trong **một read-write transaction**.

Bài thuộc chương **Spanner**, trong học phần **CLOUD_PROVIDERS_GCP**: học cách lựa chọn database, bảo vệ tài nguyên bằng IAM, triển khai dịch vụ Java trên Cloud Run/GKE, tự động hóa phát hành và giám sát độ tin cậy cùng chi phí. Nội dung tập trung vào **thiết kế dữ liệu và thực thi giao dịch an toàn**, không phải hướng dẫn kế toán tài chính đầy đủ.

Sau bài này, bạn có thể:

- Xác định bất biến sổ kép, idempotency, tính nguyên tử và quy tắc không âm số dư.
- Thiết kế schema GoogleSQL gồm `Accounts`, `Transfers` và `LedgerEntries`, tránh khóa tăng tuần tự.
- Dùng read-write transaction của Spanner để ghi hai ledger entries cùng cập nhật hai số dư.
- Viết Java client sử dụng **ADC**, `TransactionRunner`, DML có bind parameters và xử lý retry/commit timestamp.
- Kiểm tra bằng SQL: tổng biến động bằng 0, đối soát số dư, tìm giao dịch lặp và truy vấn lịch sử.
- Nhận diện hạn chế của sổ tiền tệ, tranh chấp tài khoản nóng, index hotspots, IAM và chi phí.
- Thử giao dịch đồng thời, request timeout, chuyển nhầm tenant và kế hoạch khắc phục/rollback.

> **An toàn:** Đây là mô hình đào tạo, **không phải hệ thống thanh toán đã đạt kiểm toán hoặc chứng nhận tuân thủ**. Không dùng dữ liệu tiền thật. Mỗi lệnh tạo Spanner instance có thể phát sinh chi phí; chỉ chạy trong project lab được cấp quyền.

## 1. Bất biến sổ kép và phạm vi bài lab

Với một lệnh chuyển tiền nội bộ có cùng đơn vị tiền tệ:

~~~text
Trước giao dịch:
  A = 100,00 USD = 10.000 cents
  B =   5,00 USD =    500 cents

Chuyển 25,00 USD (2.500 cents):
  LedgerEntries:
    A: -2500
    B: +2500

Sau commit:
  A =  7.500 cents =  75,00 USD
  B =  3.000 cents =  30,00 USD

Tổng biến động: (-2500) + (+2500) = 0
~~~

Bốn bất biến chính:

1. **Cân bằng:** mỗi transfer có **đúng hai** entry, cùng tiền tệ, một âm một dương, tổng `DeltaMinor = 0`.
2. **Nguyên tử:** cập nhật `BalanceMinor` của A/B và ghi cả hai ledger entries **cùng commit hoặc cùng rollback**.
3. **Không chi vượt:** tài khoản nguồn chỉ chuyển khi trạng thái hợp lệ và đủ số dư. Với business cho phép thấu chi, đây phải là quy tắc riêng chứ không vô hiệu hóa kiểm tra âm bừa bãi.
4. **Idempotency:** cùng `RequestId` gửi lại với **cùng payload** không chuyển thêm lần nữa; gửi lại `RequestId` với payload khác phải bị từ chối.

**Quy ước thuật ngữ:** `DeltaMinor < 0` nghĩa là giảm số dư nguồn, `DeltaMinor > 0` là tăng số dư đích. Đây là mô hình **chuyển giữa hai tài khoản cùng loại**; trong kế toán tổng quát, “debit”/“credit” phụ thuộc loại tài khoản và dấu không được đồng nhất máy móc với Nợ/Có. Chuyển **khác tiền tệ** cần tỷ giá, tài khoản bù trừ và nghiệp vụ FX riêng, không thể chỉ ghi `-100 USD` và `+100 EUR` rồi coi cân bằng.

### Vì sao dùng đơn vị tiền tệ nhỏ nhất?

`AmountMinor INT64` lưu số nguyên theo *minor unit* của đồng tiền: USD dùng cents (2 chữ số sau dấu phẩy), VND thông thường dùng đồng (0 chữ số). Cách này tránh sai số của `FLOAT64` và giúp so sánh số dư chính xác. Với hóa đơn/tiền lãi cần độ chính xác hoặc scale khác, cân nhắc `NUMERIC` (decimal exact theo giới hạn Spanner), quy tắc rounding và kiểm tra overflow; **không dùng floating point** cho số tiền.

## 2. Thiết kế dữ liệu: ba bảng và một index

~~~mermaid
flowchart LR
  A["Accounts<br/>AccountId PK<br/>OpeningBalanceMinor<br/>BalanceMinor"] 
  T["Transfers<br/>RequestId PK<br/>AmountMinor<br/>PostedAt"]
  L["LedgerEntries<br/>RequestId + LineNo PK<br/>AccountId, DeltaMinor"]
  T -->|"mỗi transfer có 2 entries"| L
  L -->|"biến động của"| A
~~~

| Bảng | Mục đích | Lưu ý thiết kế |
|---|---|---|
| `Accounts` | Số dư hiện tại và số dư đầu kỳ được kiểm toán | Không dùng số dư trong cache làm nguồn dữ liệu duy nhất |
| `Transfers` | Một chứng từ chuyển tiền duy nhất theo `RequestId` | PK chống tạo trùng chứng từ; lưu payload để phát hiện key bị tái sử dụng sai |
| `LedgerEntries` | Hai biến động bất biến cho mỗi transfer | Khóa `(RequestId, LineNo)` và `DeltaMinor` có dấu |
| `LedgerEntriesByAccount` | Tra biến động theo tài khoản | Thêm index khi pattern đọc cần; theo dõi write amplification |

`RequestId` phải là UUID v4 hoặc định danh **phân bố ngẫu nhiên, duy nhất toàn hệ thống**, được tạo **trước** khi gọi transaction và tái dùng khi request được gửi lại. Không lấy commit timestamp hoặc sequence tăng dần làm tiền tố khóa chính ở bảng ghi nhiều vì dễ tạo **hotspot** trên cùng dải khóa.

Để dễ đối soát dữ liệu được chuyển từ hệ thống cũ, bảng `Accounts` có `OpeningBalanceMinor`. Trong lab hai tài khoản được **seed** với opening balance đã chấp thuận. Trong sản phẩm mới, tốt hơn là thiết kế **bút toán mở sổ có kiểm toán**; không cho người dùng tùy ý sửa opening balance. Đối soát phải tính số dư đầu kỳ + mọi biến động kể từ thời điểm mở sổ.

### GoogleSQL DDL

Lưu dưới tên `schema.sql` trong **thư mục lab riêng** của người học. Đây là **Spanner GoogleSQL dialect**, không phải PostgreSQL dialect.

~~~sql
CREATE TABLE Accounts (
  AccountId STRING(36) NOT NULL,
  TenantId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  OpeningBalanceMinor INT64 NOT NULL,
  BalanceMinor INT64 NOT NULL,
  Status STRING(16) NOT NULL,
  CONSTRAINT balance_not_negative CHECK (BalanceMinor >= 0)
) PRIMARY KEY (AccountId);

CREATE TABLE Transfers (
  RequestId STRING(36) NOT NULL,
  TenantId STRING(36) NOT NULL,
  SourceAccountId STRING(36) NOT NULL,
  DestinationAccountId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  AmountMinor INT64 NOT NULL,
  PostedAt TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp = true),
  CONSTRAINT positive_transfer CHECK (AmountMinor > 0),
  CONSTRAINT distinct_accounts CHECK (SourceAccountId != DestinationAccountId)
) PRIMARY KEY (RequestId);

CREATE TABLE LedgerEntries (
  RequestId STRING(36) NOT NULL,
  LineNo INT64 NOT NULL,
  TenantId STRING(36) NOT NULL,
  AccountId STRING(36) NOT NULL,
  Currency STRING(3) NOT NULL,
  DeltaMinor INT64 NOT NULL,
  CONSTRAINT nonzero_entry CHECK (DeltaMinor != 0)
) PRIMARY KEY (RequestId, LineNo);

CREATE INDEX LedgerEntriesByAccount
ON LedgerEntries (AccountId, RequestId)
STORING (DeltaMinor, TenantId, Currency);
~~~

**Giới hạn bảo vệ dữ liệu trong schema này:** `CHECK` có thể ràng buộc giá trị **cùng một hàng**, nhưng không kiểm tra được “hai entries cùng RequestId phải có tổng 0”. Bất biến xuyên hàng cần thực thi trong **transaction write path** và kiểm tra bằng **reconciliation**. Trong production nên bổ sung kiểm soát đường ghi (không cấp quyền DML thẳng cho nhiều ứng dụng), quyền đọc theo tenant, audit và quy trình sửa sai bằng *compensating entries*.

**Vì sao không đặt `PostedAt` lên đầu primary key?** Timestamp tăng đều dồn insert về cuối key range và tạo hotspot. `RequestId` random phân phối writes; `PostedAt` lưu **commit timestamp** phục vụ audit/sắp xếp. Secondary index theo timestamp toàn cục cũng có thể trở thành hotspot; chỉ thêm khi thực sự cần và có chiến lược phân vùng.

## 3. Chuẩn bị Spanner instance/database và dữ liệu thử

Lab dùng cấu hình regional Singapore; chọn instance configuration **thực sự được hỗ trợ** ở project/edition của bạn và cân nhắc data residency. Cần billing, quyền Spanner Instance Admin/Database Admin phù hợp, `gcloud` và Java 17+.

~~~bash
PROJECT_ID="my-spanner-ledger-lab"
INSTANCE="ledger-lab"
DATABASE="ledger"

gcloud config set project "$PROJECT_ID"
gcloud services enable spanner.googleapis.com

# Thử nghiệm: chỉ tạo instance mới trong project lab.
gcloud spanner instances create "$INSTANCE" \
  --config="regional-asia-southeast1" \
  --description="Double-entry ledger lab" \
  --processing-units=100

gcloud spanner databases create "$DATABASE" \
  --instance="$INSTANCE" \
  --database-dialect=GOOGLE_STANDARD_SQL

gcloud spanner databases ddl update "$DATABASE" \
  --instance="$INSTANCE" \
  --ddl-file="schema.sql"

# Chỉ đọc schema; chờ DDL operation hoàn tất trước khi ghi.
gcloud spanner databases ddl describe "$DATABASE" \
  --instance="$INSTANCE"
~~~

**Lưu ý:** processing units và edition quyết định công suất tối thiểu/khả năng tính năng; nếu cấu hình 100 PU không khả dụng trong project/edition, chọn mức được phép theo tài liệu/quota hiện hành. Không chuyển sang instance production để “thử cho nhanh”.

### Seed dữ liệu mở sổ

Dùng **hai UUID v4 cố định cho lab** (không dùng các ID dưới đây cho production). Giả sử khoản mở sổ đến từ snapshot hệ thống cũ đã được kiểm toán:

~~~text
Tenant: tenant-demo
A: 782e6ff2-965e-4668-960a-10493863f5c2
B: 3f4cbb77-3a16-467f-b357-0c5573a047ed
Currency: USD
Opening balances: 10000 cents và 500 cents
~~~

~~~sql
INSERT INTO Accounts (
  AccountId, TenantId, Currency,
  OpeningBalanceMinor, BalanceMinor, Status
)
VALUES
  ("782e6ff2-965e-4668-960a-10493863f5c2",
   "tenant-demo", "USD", 10000, 10000, "ACTIVE"),
  ("3f4cbb77-3a16-467f-b357-0c5573a047ed",
   "tenant-demo", "USD", 500, 500, "ACTIVE");
~~~

Trong Spanner Studio, thực thi SQL seed **một lần** ở database lab. Có thể chạy DML bằng `gcloud spanner databases execute-sql` với `--sql` nếu phù hợp phiên bản CLI. Không dùng `INSERT OR UPDATE` hoặc `INSERT OR IGNORE` để sửa seed ngoài ý muốn; DML `INSERT` nên lỗi nếu dữ liệu đã có.

**Số dư mở sổ không phải tiền được tạo từ hư không:** trong hệ thống kế toán hoàn chỉnh, các số dư phải được đối chiếu với nguồn vốn, liabilities và tài liệu migration. Bài này chỉ xét **các biến động sau snapshot**, vì vậy ở mục đối soát sẽ có `OpeningBalanceMinor` trong công thức.

## 4. Java: ghi sổ trong một read-write transaction

Đường ghi duy nhất có trách nhiệm: **xác thực tenant ở HTTP/API layer → kiểm tra dữ liệu → kiểm tra idempotency → đọc hai Accounts → tính số dư mới → ghi hai Accounts, hai LedgerEntries, một Transfers → commit**. Không có lệnh gửi Pub/Sub/HTTP thanh toán nằm **bên trong transaction callback**, vì Spanner có thể thực thi lại callback khi gặp `ABORTED`.

### Dependency và Application Default Credentials

Ví dụ dùng Java 17+, client `com.google.cloud:google-cloud-spanner`. Với Maven, khai báo dependency sau trong một project Java đã có plugin build phù hợp:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-spanner</artifactId>
    <version>6.124.0</version>
  </dependency>
</dependencies>
~~~

Phiên bản trên là một bản API 6.x để minh họa, không phải yêu cầu phải khóa vĩnh viễn; trong dự án thực tế chọn phiên bản được hỗ trợ qua Google Cloud Libraries BOM và kiểm thử. Khi chạy trên Cloud Run/GKE, client sử dụng **ADC** của runtime service account; khi chạy local có thể dùng `gcloud auth application-default login` trong project lab.

### Lớp `LedgerDemo`: đọc, cập nhật và chống chuyển trùng

Đặt file trong `src/main/java/example/LedgerDemo.java`. Các import, kiểu dữ liệu và đường ghi được trình bày đầy đủ để có thể ghép vào một Maven project:

~~~java
package example;

import com.google.cloud.spanner.DatabaseClient;
import com.google.cloud.spanner.DatabaseId;
import com.google.cloud.spanner.ResultSet;
import com.google.cloud.spanner.Spanner;
import com.google.cloud.spanner.SpannerOptions;
import com.google.cloud.spanner.Statement;
import com.google.cloud.spanner.TransactionContext;
import java.util.UUID;

public final class LedgerDemo {
    private final DatabaseClient db;

    public LedgerDemo(DatabaseClient db) {
        this.db = db;
    }

    public record Request(
        String requestId, String tenantId, String from, String to,
        String currency, long amountMinor) {}

    public record Receipt(String requestId, String status) {}

    private record Account(
        String tenantId, String currency, String status, long balanceMinor) {}

    public Receipt transfer(Request r) {
        // Kiểm tra dữ liệu đầu vào và quyền tenant tại API boundary.
        if (r.amountMinor() <= 0 || r.from().equals(r.to())
                || UUID.fromString(r.requestId()).version() != 4) {
            throw new IllegalArgumentException("Invalid transfer request");
        }

        // TransactionRunner có thể gọi lại callback sau ABORTED.
        return db.readWriteTransaction().run(tx -> {
            // 1. RequestId là khóa idempotency; nếu đã ghi, so khớp payload.
            Statement existingQuery = Statement.newBuilder(
                "SELECT TenantId, SourceAccountId, DestinationAccountId, "
                + "Currency, AmountMinor FROM Transfers "
                + "WHERE RequestId = @requestId")
                .bind("requestId").to(r.requestId())
                .build();
            try (ResultSet existing = tx.executeQuery(existingQuery)) {
                if (existing.next()) {
                    boolean samePayload =
                        existing.getString("TenantId").equals(r.tenantId())
                        && existing.getString("SourceAccountId").equals(r.from())
                        && existing.getString("DestinationAccountId").equals(r.to())
                        && existing.getString("Currency").equals(r.currency())
                        && existing.getLong("AmountMinor") == r.amountMinor();
                    if (!samePayload) {
                        throw new IllegalArgumentException(
                            "Idempotency key reused with different payload");
                    }
                    return new Receipt(r.requestId(), "ALREADY_POSTED");
                }
            }

            // 2. Đọc hai tài khoản cùng transaction.
            Account source = getAccount(tx, r.from());
            Account destination = getAccount(tx, r.to());
            requireActive(source, r);
            requireActive(destination, r);

            long newSource = Math.subtractExact(
                source.balanceMinor(), r.amountMinor());
            long newDestination = Math.addExact(
                destination.balanceMinor(), r.amountMinor());
            if (newSource < 0) {
                throw new IllegalArgumentException("Insufficient funds");
            }

            // 3. Hai bản cập nhật số dư nằm trong CÙNG transaction.
            updateBalance(tx, r.from(), newSource);
            updateBalance(tx, r.to(), newDestination);

            // 4. Hai biến động trái dấu, cùng RequestId/Currency.
            insertEntry(tx, r, 1L, r.from(), -r.amountMinor());
            insertEntry(tx, r, 2L, r.to(), r.amountMinor());

            // 5. Ghi chứng từ với commit timestamp ở LỆNH DML CUỐI.
            // Không đọc lại bảng Transfers sau PENDING_COMMIT_TIMESTAMP().
            mustWriteOne(tx, Statement.newBuilder("""
                INSERT INTO Transfers (
                    RequestId, TenantId, SourceAccountId,
                    DestinationAccountId, Currency, AmountMinor, PostedAt
                ) VALUES (
                    @requestId, @tenantId, @sourceId,
                    @targetId, @currency, @amount, PENDING_COMMIT_TIMESTAMP()
                )
                """)
                .bind("requestId").to(r.requestId())
                .bind("tenantId").to(r.tenantId())
                .bind("sourceId").to(r.from())
                .bind("targetId").to(r.to())
                .bind("currency").to(r.currency())
                .bind("amount").to(r.amountMinor())
                .build());

            // Chỉ được trả kết quả cho caller sau khi commit thành công.
            return new Receipt(r.requestId(), "POSTED");
        });
    }

    private static Account getAccount(TransactionContext tx, String id) {
        Statement q = Statement.newBuilder("""
            SELECT TenantId, Currency, Status, BalanceMinor
            FROM Accounts WHERE AccountId = @accountId
            """)
            .bind("accountId").to(id)
            .build();
        try (ResultSet rows = tx.executeQuery(q)) {
            if (!rows.next()) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                rows.getString("TenantId"),
                rows.getString("Currency"),
                rows.getString("Status"),
                rows.getLong("BalanceMinor"));
        }
    }

    private static void requireActive(Account a, Request r) {
        if (!a.tenantId().equals(r.tenantId())
                || !a.currency().equals(r.currency())
                || !a.status().equals("ACTIVE")) {
            throw new IllegalArgumentException(
                "Account not permitted or wrong currency");
        }
    }

    private static void updateBalance(
            TransactionContext tx, String accountId, long newBalance) {
        mustWriteOne(tx, Statement.newBuilder("""
            UPDATE Accounts SET BalanceMinor = @balance
            WHERE AccountId = @accountId
            """)
            .bind("balance").to(newBalance)
            .bind("accountId").to(accountId)
            .build());
    }

    private static void insertEntry(
            TransactionContext tx, Request r, long lineNo,
            String accountId, long signedDelta) {
        mustWriteOne(tx, Statement.newBuilder("""
            INSERT INTO LedgerEntries (
                RequestId, LineNo, TenantId, AccountId,
                Currency, DeltaMinor
            ) VALUES (
                @requestId, @lineNo, @tenantId, @accountId,
                @currency, @delta
            )
            """)
            .bind("requestId").to(r.requestId())
            .bind("lineNo").to(lineNo)
            .bind("tenantId").to(r.tenantId())
            .bind("accountId").to(accountId)
            .bind("currency").to(r.currency())
            .bind("delta").to(signedDelta)
            .build());
    }

    private static void mustWriteOne(
            TransactionContext tx, Statement statement) {
        if (tx.executeUpdate(statement) != 1L) {
            throw new IllegalStateException("Expected exactly one row");
        }
    }

    public static void main(String[] args) {
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "Usage: PROJECT_ID INSTANCE_ID DATABASE_ID REQUEST_UUID_V4");
        }
        String project = args[0];
        String instance = args[1];
        String database = args[2];
        String requestId = args[3];
        Spanner spanner = SpannerOptions.newBuilder()
            .setProjectId(project).build().getService();
        try {
            DatabaseClient client = spanner.getDatabaseClient(
                DatabaseId.of(project, instance, database));
            Request req = new Request(
                requestId, "tenant-demo",
                "782e6ff2-965e-4668-960a-10493863f5c2",
                "3f4cbb77-3a16-467f-b357-0c5573a047ed",
                "USD", 2500L);
            Receipt receipt = new LedgerDemo(client).transfer(req);
            System.out.println(receipt);
        } finally {
            spanner.close();
        }
    }
}
~~~

Điểm quan trọng:

- `TransactionRunner` của Spanner **tự retry transaction khi ABORTED**, nên callback phải **không có side effect ngoài Spanner**, ví dụ không gửi email hoặc gọi payment API trong đó.
- `SELECT Transfers WHERE RequestId = ...` và `INSERT Transfers` nằm trong cùng transaction, giúp serializable isolation xử lý các request tranh chấp; primary key đảm bảo không có hai chứng từ cùng ID. Với lỗi đua/timeout đặc biệt, caller có thể **truy vấn chứng từ theo RequestId** trước khi quyết định gửi lại.
- `PENDING_COMMIT_TIMESTAMP()` là DML expression được Spanner thay bằng commit timestamp; không thể dùng như `CURRENT_TIMESTAMP()` thông thường. Sau khi gọi hàm này, không đọc lại bảng liên quan trong cùng transaction — vì vậy để **lệnh ghi Transfers cuối cùng**.
- `Math.subtractExact` và `Math.addExact` phát hiện overflow `INT64` ở Java thay vì âm thầm làm sai số tiền; input validation phải kiểm tra thêm độ dài ID, currency code và authentication của caller trước khi gọi `transfer`.
- Trong schema, `Accounts` được cập nhật bằng DML, không trộn DML với mutations mà chưa hiểu thứ tự/visibility.

### Chạy Java trong project lab

Người học cần file Java, `pom.xml` đã có dependency và plugin thực thi phù hợp. Có thể dùng Maven Exec Plugin được cấu hình trong project:

~~~bash
# Cần application ADC khi chạy LOCAL (không thực hiện trên Cloud Run):
gcloud auth application-default login

# Giữ nguyên UUID khi retry; KHÔNG tạo UUID mới cho lần gửi lại.
REQUEST_ID="5fe632ac-e86b-49f5-8f83-ac429bb278df"

mvn -q compile exec:java \
  -Dexec.mainClass=example.LedgerDemo \
  -Dexec.args="my-spanner-ledger-lab ledger-lab ledger $REQUEST_ID"
~~~

Lần đầu kỳ vọng `Receipt[..., status=POSTED]`; chạy lại **cùng lệnh** kỳ vọng `ALREADY_POSTED`, không trừ tiền thêm. Nếu chạy trên môi trường đã seed hoặc ghi giao dịch trước đó, truy vấn số dư và journal trước khi thử để tránh kết luận sai.

## 5. Đọc sổ và đối soát dữ liệu bằng SQL

Spanner hỗ trợ **strongly consistent reads**; một read-only transaction có thể đọc snapshot nhất quán trên nhiều bảng, trong khi read-write transaction mặc định có tính **serializable/external consistency**. Đọc hai số dư qua hai request tách biệt không có snapshot chung có thể thấy hai thời điểm khác nhau, nên **đọc sổ cần nhất quán** khi lập báo cáo kiểm toán.

### Xác minh số dư, transfer và entries

Sau một transfer 2.500 cents từ A tới B:

~~~sql
-- Kỳ vọng A = 7500, B = 3000.
SELECT AccountId, Currency, OpeningBalanceMinor, BalanceMinor
FROM Accounts
WHERE TenantId = "tenant-demo"
ORDER BY AccountId;

-- Chứng từ, commit timestamp và payload phục vụ dedup.
SELECT RequestId, SourceAccountId, DestinationAccountId,
       Currency, AmountMinor, PostedAt
FROM Transfers
WHERE RequestId = "5fe632ac-e86b-49f5-8f83-ac429bb278df";

-- Hai biến động cùng RequestId.
SELECT RequestId, LineNo, AccountId, DeltaMinor, Currency
FROM LedgerEntries
WHERE RequestId = "5fe632ac-e86b-49f5-8f83-ac429bb278df"
ORDER BY LineNo;
~~~

| Kiểm tra | Giá trị sau lần gửi đầu | Sau gửi lại cùng ID |
|---|---:|---:|
| Số dư A | 7.500 cents | 7.500 cents |
| Số dư B | 3.000 cents | 3.000 cents |
| Số chứng từ có RequestId đó | 1 | 1 |
| Số `LedgerEntries` của RequestId | 2 | 2 |
| Tổng `DeltaMinor` của hai entries | 0 | 0 |

### Đối soát tổng biến động mỗi transfer

~~~sql
-- Trả về các chứng từ thiếu dòng, thừa dòng hoặc không cân bằng.
-- Kết quả mong đợi: 0 hàng với dữ liệu hợp lệ.
SELECT
  t.RequestId,
  COUNT(e.LineNo) AS EntryCount,
  IFNULL(SUM(e.DeltaMinor), 0) AS NetMinor
FROM Transfers AS t
LEFT JOIN LedgerEntries AS e ON t.RequestId = e.RequestId
GROUP BY t.RequestId
HAVING COUNT(e.LineNo) != 2
   OR IFNULL(SUM(e.DeltaMinor), 0) != 0;
~~~

Query này còn cần mở rộng để kiểm tra **đúng tài khoản nguồn/đích, tenant, currency và dấu** của từng entry. Có hai dòng có tổng bằng 0 **chưa chứng minh** chúng là hai biến động hợp lệ cho cùng giao dịch.

### Đối soát số dư mở sổ cộng biến động

~~~sql
-- Tìm tài khoản có số dư khác với opening balance + entries.
-- Kết quả mong đợi: 0 hàng.
SELECT
  a.AccountId,
  a.BalanceMinor,
  a.OpeningBalanceMinor + IFNULL(SUM(e.DeltaMinor), 0) AS ExpectedMinor
FROM Accounts AS a
LEFT JOIN LedgerEntries AS e ON a.AccountId = e.AccountId
GROUP BY a.AccountId, a.BalanceMinor, a.OpeningBalanceMinor
HAVING a.BalanceMinor
    != a.OpeningBalanceMinor + IFNULL(SUM(e.DeltaMinor), 0);
~~~

Với lượng lịch sử lớn, không chạy truy vấn quét toàn bộ `LedgerEntries` liên tục trên production. Thay bằng **reconciliation theo ngày/partition**, snapshot được kiểm toán, hoặc batch read có giới hạn tải. Để công bố số dư cho người dùng, có thể đọc `Accounts.BalanceMinor` qua strong read; khi đối soát định kỳ phải dựa trên lịch sử entries và opening snapshot.

### Truy vấn lịch sử một tài khoản

~~~sql
SELECT e.RequestId, t.PostedAt, e.DeltaMinor, e.Currency
FROM LedgerEntries AS e
JOIN Transfers AS t ON t.RequestId = e.RequestId
WHERE e.AccountId = "782e6ff2-965e-4668-960a-10493863f5c2"
ORDER BY t.PostedAt DESC, e.RequestId DESC
LIMIT 20;
~~~

Index `LedgerEntriesByAccount` giúp giới hạn scan theo `AccountId`. Tuy nhiên nó **không tự sắp xếp theo `PostedAt`**, vì timestamp nằm ở bảng `Transfers`; query có thể phải join/sort nhiều entries. Khi xây lịch sử giao dịch ở quy mô lớn, thiết kế **read model/index riêng theo AccountId + time** và đánh giá thêm write amplification/hotspots, không lập index timestamp tăng dần toàn cục một cách vô thức.

## 6. Kiểm thử bắt buộc: lỗi, retry và tranh chấp đồng thời

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| **T1 — Chuyển hợp lệ** | Tạo RequestId v4, chuyển 2500 cents | Số dư đổi -2500/+2500, 1 transfer, 2 entries |
| **T2 — Gửi lại cùng request** | Giữ nguyên RequestId và toàn bộ payload | `ALREADY_POSTED`; không thêm entries |
| **T3 — Tái dùng key với payload khác** | Cùng RequestId nhưng amount/account khác | Từ chối, không đổi số dư |
| **T4 — Thiếu tiền** | Tạo RequestId mới, chuyển lớn hơn BalanceMinor nguồn | Thất bại; không có transfer/entries nửa chừng |
| **T5 — Sai tenant/currency** | Lấy account khác tenant hoặc USD → EUR | Từ chối trước commit |
| **T6 — Đầu vào âm hoặc source = target** | AmountMinor 0/âm, cùng account | Validation từ chối |
| **T7 — Tranh chấp một số dư** | Hai request đồng thời, mỗi request riêng lẻ đủ tiền nhưng cộng lại vượt số dư | Không để cả hai commit làm số dư âm; một transaction có thể bị `ABORTED`/retry rồi thất bại thiếu tiền |
| **T8 — Timeout sau commit** | Client không nhận response nhưng server đã ghi thành công; gửi lại ID cũ | Truy vấn Transfers thấy chứng từ cũ; không trừ thêm |
| **T9 — Overflow** | Giá trị gần `Long.MAX_VALUE` | Java `Math.addExact/subtractExact` hoặc constraint chặn |
| **T10 — Khôi phục/report** | Chạy hai query reconciliation | Không có hàng vi phạm |

### Vì sao Spanner chịu được race ở số dư?

~~~mermaid
sequenceDiagram
  participant R1 as Request 1
  participant SP as Spanner
  participant R2 as Request 2
  R1->>SP: Đọc A=5000; dự kiến trừ 4000
  R2->>SP: Đọc A=5000; dự kiến trừ 4000
  R1->>SP: Ghi số dư + entries + commit
  SP-->>R1: COMMITTED
  R2->>SP: Commit với dữ liệu đọc cũ
  SP-->>R2: ABORTED / yêu cầu retry
  R2->>SP: Đọc lại A=1000
  SP-->>R2: Không đủ 4000 → từ chối
~~~

Đây là trình tự minh họa, không khẳng định transaction nào luôn thắng. **Read-write transaction mặc định serializable** và client Java tự retry khi gặp `ABORTED`, nên lần thử lại thấy số dư cập nhật. Nếu dùng transaction isolation hoặc đường ghi khác, cần xác minh lại bất biến tương ứng.

**Tuyệt đối không** dùng `Partitioned DML` để cập nhật số dư/entries từng phần: Partitioned DML không mang tính nguyên tử như một giao dịch chuyển tiền đơn lẻ và có thể áp dụng thay đổi theo partition; nó phù hợp những cập nhật hàng loạt có tính idempotent, không phù hợp multi-row ledger posting. Không đưa lệnh gửi Pub/Sub, charge qua cổng thanh toán hoặc log nghiệp vụ mang side effect vào callback tự retry.

## 7. Audit bất biến, chỉnh sai và phát sự kiện

### Không sửa lịch sử bằng cách ghi đè

Trong bài lab, chỉ **insert** `Transfers` và `LedgerEntries` khi chuyển tiền; nếu nghiệp vụ cần hoàn tiền 25,00 USD, tạo **transfer bù trừ mới** với RequestId riêng, chuyển từ B về A. Gắn trường tham chiếu `OriginalRequestId` trong schema mở rộng và giữ lý do bù trừ, người phê duyệt, timestamp.

**Không** chạy `UPDATE LedgerEntries SET DeltaMinor=...` hoặc `DELETE FROM Transfers ...` để “sửa sổ”; điều đó phá audit trail. Spanner có transaction consistency mạnh nhưng **không tự tạo immutable/legal audit ledger**: quyền IAM, change tracking, hash/audit trail và chính sách lưu trữ phải do hệ thống thiết kế.

### Outbox và Change Streams

Sau commit cần gửi `transfer-posted` đến Pub/Sub để service thông báo xử lý. Nếu gửi Pub/Sub **sau commit**, có thể xảy ra tình huống DB thành công nhưng publish thất bại; nếu gửi **trước commit**, có thể phát thông điệp cho transfer đã rollback.

Hướng giải quyết:

- Ghi một bản ghi **OutboxEvents** trong **cùng Spanner transaction**, rồi worker đọc/publish và đánh dấu trạng thái (retry/idempotency ở consumer).
- Hoặc dùng **Spanner change streams** theo khả năng hỗ trợ để thu thập các thay đổi đã commit, rồi đưa tới Dataflow/Pub/Sub downstream; phải thiết kế at-least-once và thứ tự theo business key.

Không khẳng định **exactly-once end-to-end** chỉ vì Spanner transaction atomic. Ở hệ thống phân tán, consumer vẫn phải chống xử lý trùng bằng event ID/business key.

### Thời gian commit và truy xuất lịch sử

`PostedAt TIMESTAMP OPTIONS (allow_commit_timestamp=true)` ghi thời điểm Spanner commit. **Commit timestamp không phải ID duy nhất**; các transaction độc lập có thể trùng timestamp, do đó dùng `RequestId` để phân biệt và sắp thứ tự phụ. Với các báo cáo từ nhiều query, dùng snapshot/read-only transaction phù hợp để tránh ghép dữ liệu ở những thời điểm khác nhau.

## 8. Scale: primary keys, tài khoản nóng và query

Spanner phân phối dữ liệu theo key ranges. Dù có khả năng mở rộng mạnh, schema vẫn có thể gây nóng một range hoặc một row:

| Sai lầm | Hậu quả | Hướng khắc phục |
|---|---|---|
| PK `(PostedAt, RequestId)` | Timestamp tăng dồn inserts vào cuối keyspace | RequestId UUID v4, timestamp là cột khác |
| RequestId tăng tuần tự hoặc UUID v1 | Các writes gần nhau về thứ tự key | UUID v4/phân bố ngẫu nhiên; hoặc sequence bit-reversed đúng chuẩn |
| Mọi transfer cùng chạm **một tài khoản trung tâm** | Cùng một row balance bị tranh chấp, nhiều abort/latency | Thiết kế subledger/shard theo nghiệp vụ, đối soát tổng và chấp nhận đánh đổi về consistency |
| Index toàn cục bắt đầu bằng timestamp tăng | Hotspot ở secondary index | Đổi thứ tự index, dùng prefix account/shard khi đúng truy vấn |
| Quét lịch sử vài tỷ entries cho mỗi request | Chi phí và latency rất cao | Balance materialization, read models, partition/batch reconciliation |
| Transaction chứa HTTP call hoặc xử lý dài | Giữ locks, tăng abort và thời gian commit | Chỉ kiểm tra/ghi DB trong callback; external orchestration ở ngoài |

**Không shard một số dư duy nhất bằng cách cộng các số dư shard tùy ý** nếu yêu cầu chặn chi vượt theo thời gian thực: thao tác cần bảo toàn bất biến đủ tiền dưới tranh chấp, và tổng shard có thể không đủ để ngăn chi vượt khi không có giao thức phối hợp. Với ví điện tử có một tài khoản nhận hàng chục nghìn transfers/giây, phải benchmark và thiết kế riêng thay vì mặc định một row Spanner là vô hạn.

Khi lượng dữ liệu tăng, xem **Key Visualizer**, transaction statistics, lock/abort metrics, CPU utilization, query insights và query plans để tìm hotspots. Trước khi thêm index, so sánh lợi ích đọc với số lượng mutations/index entries phải ghi thêm mỗi transfer.

## 9. IAM, mạng và triển khai ứng dụng Java trên GCP

| Danh tính | Vai trò | Quyền tham khảo |
|---|---|---|
| Platform/DB administrator | Tạo instance/database, DDL, backup/restore | Spanner Instance Admin/Database Admin theo scope và phê duyệt |
| Java Cloud Run/GKE runtime service account | Ghi/chỉ đọc sổ theo nhiệm vụ | `roles/spanner.databaseUser` trên **database cụ thể** nếu chấp nhận tập quyền này |
| Reconciliation worker | Đọc snapshot/báo cáo | Role chỉ đọc hoặc **Spanner fine-grained access control** theo database role |
| CI/CD deployer | Build/deploy Java runtime | Cloud Run deploy và quyền `iam.serviceAccounts.actAs` trên runtime SA |
| Auditor | Xem báo cáo và audit logs | Các role chỉ đọc/log reader được phê duyệt |

**Chú ý quyền mạnh:** `roles/spanner.databaseUser` cung cấp nhiều quyền vận hành SQL, **bao gồm khả năng thay đổi schema** theo bộ quyền hiện hành; đối với sổ tiền thật cần xét **custom IAM role** hoặc **Spanner fine-grained access control** và phân tách schema migrations khỏi account posting. Không cấp `roles/spanner.databaseAdmin` hoặc Owner cho ứng dụng chỉ để ghi hai ledger entries.

Ví dụ gán IAM ở **database** thay vì toàn project:

~~~bash
PROJECT_ID="my-spanner-ledger-lab"
INSTANCE="ledger-lab"
DATABASE="ledger"
RUNTIME_SA="orders-ledger@$PROJECT_ID.iam.gserviceaccount.com"

# Cần tạo runtime SA và kiểm tra IAM policy trước, không tạo trùng.
gcloud spanner databases add-iam-policy-binding "$DATABASE" \
  --instance="$INSTANCE" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/spanner.databaseUser" \
  --project="$PROJECT_ID"

gcloud spanner databases get-iam-policy "$DATABASE" \
  --instance="$INSTANCE" --project="$PROJECT_ID"
~~~

Đây là ví dụ thao tác IAM trong lab. Với production, review role quá rộng và có quy trình phê duyệt. Java sử dụng **Application Default Credentials (ADC)** của runtime SA, không tải JSON key. Nếu Java trên GKE, dùng **Workload Identity Federation for GKE**; trên Cloud Run, cấu hình `--service-account` cho revision.

**Mạng:** các Spanner client libraries gọi Spanner API qua gRPC/TLS. Workload cần egress tới Google Cloud APIs theo chính sách mạng. Private Google Access, PSC for Google APIs hoặc VPC Service Controls có thể được sử dụng theo kiến trúc tổ chức; **Spanner không đòi cấu hình Cloud SQL Private Services Access** và không dùng Cloud SQL Auth Proxy/Cloud SQL JDBC SocketFactory. Xác thực IAM và network path là hai điều kiện riêng.

**Phân quyền theo tenant:** IAM database-level không tự kiểm tra `tenant-demo` trong từng request của Java. Trước khi gọi `transfer` phải xác thực caller và lấy `tenantId` từ danh tính đã kiểm chứng; không tin một chuỗi tenant ID do client gửi mà chưa đối chiếu. Truy vấn đọc tài khoản cũng phải được lọc/ủy quyền đúng owner/tenant, không dựa vào việc biết AccountId.

## 10. Emulator, CI/CD, backup và audit

### Dùng Spanner emulator để kiểm thử logic

Emulator chạy local, lưu dữ liệu trong **RAM** và mất dữ liệu khi restart; hỗ trợ API GoogleSQL/PostgreSQL nhưng **không mô phỏng đầy đủ IAM, TLS, performance, schema/transaction locking và mọi giới hạn của production**.

~~~bash
# Terminal 1:
gcloud components install cloud-spanner-emulator
gcloud emulators spanner start

# Terminal 2: cấu hình gcloud riêng, tránh ghi đè production config.
gcloud config configurations create spanner-emulator-lab
gcloud config configurations activate spanner-emulator-lab
gcloud config set auth/disable_credentials true
gcloud config set project emulator-project
gcloud config set api_endpoint_overrides/spanner http://localhost:9020/

gcloud spanner instances create ledger-emulator \
  --config=emulator-config \
  --description="Local ledger emulator" \
  --nodes=1
gcloud spanner databases create ledger \
  --instance=ledger-emulator
gcloud spanner databases ddl update ledger \
  --instance=ledger-emulator \
  --ddl-file=schema.sql

# Java client sử dụng gRPC emulator endpoint.
export SPANNER_EMULATOR_HOST="localhost:9010"
~~~

Sau khi test, đổi về gcloud configuration bình thường:

~~~bash
gcloud config configurations activate default
unset SPANNER_EMULATOR_HOST
~~~

**Không chạy lệnh xóa trong CLI config chưa kiểm tra.** Với Windows PowerShell, cách khai báo môi trường khác Bash (`$env:SPANNER_EMULATOR_HOST = "localhost:9010"`). Emulator không thay integration test trên database Spanner thật để đánh giá concurrency/abort, IAM, throughput, latency và cost.

### CI/CD và vận hành dữ liệu

1. Review SQL DDL/migrations bằng Git, kiểm tra schema changes với dữ liệu lớn, rollback plan và quyền deploy riêng.
2. Chạy **unit tests** cho validation, idempotency và số học; chạy integration tests trên emulator với dữ liệu giả.
3. Chạy **staging Spanner thực** để test read-write retries, IAM, performance và race dưới tải.
4. Deploy Java service canary; quan sát lỗi 5xx/ABORTED, latency và đối soát. Không thay đổi ledger schema cùng lúc nhiều thành phần mà không có migration plan.
5. Thiết lập **backup/PITR**, retention/audit theo quy định, mã hóa dữ liệu, kiểm soát người được restore và chạy thử quy trình phục hồi.
6. Nếu cần phân tích/đối soát quy mô lớn, cân nhắc export/ETL có kiểm soát sang hệ thống phân tích; không khiến production OLTP chịu truy vấn full-scan liên tục.

**Khôi phục từ backup không tự giải quyết “giao dịch nào đã được gửi tới đối tác”.** Cần journal/outbox/reconciliation và đối chiếu với upstream/downstream. Đừng ghi đè database production từ snapshot cũ chỉ vì một báo cáo có lỗi.

## 11. Monitoring, độ tin cậy và chi phí

| Tín hiệu | Vì sao theo dõi |
|---|---|
| Commit latency P50/P95/P99, transaction abort rate | Lock contention hoặc latency database/network |
| Read/write CPU utilization, processing units/nodes | Dung lượng xử lý và giới hạn hiệu năng |
| Hot splits / Key Visualizer | Monotonic keys, tài khoản trung tâm, index hotspots |
| Query/transaction statistics | DML chậm, scans lớn, index không phù hợp |
| Sessions và client retry latency | Tạo client cho từng request, session exhaustion, retry storm |
| Reconciliation mismatches | Sai invariant hoặc thay đổi dữ liệu trái đường ghi chuẩn |
| IAM/DDL/audit log events | Thay đổi role, schema, cấu hình nguy hiểm |
| Storage size, backup/PITR retention, network egress | Chi phí và phục hồi |

**Phát hiện lỗi:** `ABORTED` thỉnh thoảng là cơ chế tranh chấp bình thường; tỷ lệ abort cao kèm P99 tăng hoặc workflow timeout là tín hiệu cần điều tra. Không tự tăng vô hạn số retries cho mọi lỗi; đặt **deadline và backoff** phù hợp với API/SLO, nhất là trên Cloud Run request timeout.

**Chi phí Spanner** thường liên quan tới compute capacity theo cấu hình/edition, storage, backup, replication, network và các tính năng phát sinh. Số giao dịch “1 triệu transfers/ngày” không đủ để suy ra bill nếu chưa biết processing units, instance configuration, storage footprint, write amplification từ index, query scans và retention. Trong lab, xóa instance **sau khi xác minh không cần dữ liệu** để tránh phí tiếp diễn; production cần kiểm tra drop protection, backups và owner trước khi xóa.

## 12. Runbook lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `PERMISSION_DENIED` khi Java kết nối | ADC thuộc sai SA, thiếu Spanner IAM/database role | Xác minh runtime principal, database IAM/FGAC |
| `NOT_FOUND` instance/database | Sai project/instance/database/dialect hoặc resource chưa tồn tại | `gcloud spanner instances/databases describe` |
| `ABORTED` khi transfer | Hai transactions chạm cùng Accounts row | Để TransactionRunner retry; đo contention/latency |
| Hai transfer có cùng RequestId nhưng payload khác | Client tái dùng idempotency key sai | Từ chối 409 nghiệp vụ; không sửa chứng từ đã post |
| Số dư âm hoặc `CHECK constraint failed` | Business rule không được giữ ở một đường ghi khác | Chặn đường ghi sai, audit sổ, tạo bút toán khắc phục |
| `ALREADY_EXISTS` khi ghi chứng từ | Hai requests tranh chấp hoặc key bị tái sử dụng | Đọc Transfers theo RequestId, so payload trước khi trả trạng thái |
| `RESOURCE_EXHAUSTED` / quota | Thiếu sessions/CPU/quota, bùng nổ clients | Tái dùng Spanner client, xem quotas và Key Visualizer |
| `DEADLINE_EXCEEDED` | Backend chậm, hotspot hoặc client timeout | Kiểm tra commit thực bằng RequestId; retry same ID |
| Reconciliation trả hàng vi phạm | Direct mutation, schema bug, migration/opening snapshot sai | Cô lập đường ghi, audit, không UPDATE ledger history |
| Query history chậm | Thiếu index/scan/sort dữ liệu lớn | Xem query plan, read model và index theo workload |
| Emulator chạy tốt, production lỗi | Emulator không mô phỏng IAM/performance đầy đủ | Integration test trên staging thật |
| Sau deploy nhận thiếu bảng/cột | DDL chưa hoàn tất hoặc runtime/schema version lệch | Kiểm tra migration operation, backward compatibility |

Khi không chắc request đã commit, **không tạo RequestId mới** để “gửi lại cho chắc”: query bản ghi `Transfers` theo ID cũ và dùng lại chính ID khi retry. Mapping lỗi tại HTTP boundary: dữ liệu sai `400`, thiếu quyền `403`, conflict/idempotency payload khác `409`, lỗi backend tạm thời `503` với Retry-After/backoff hợp lý; HTTP code là quyết định ứng dụng, không phải Spanner tự cung cấp toàn bộ.

## 13. Checklist trước production

- [ ] Phân biệt rõ sổ giao dịch đơn giản trong lab với sổ kế toán/pháp lý và quy tắc Nợ/Có chính thức.
- [ ] Chỉ chuyển giữa tài khoản cùng tenant/currency trong lab; không trộn FX.
- [ ] Số tiền dùng `INT64 minor units` hoặc exact decimal; chặn overflow và rounding không thống nhất.
- [ ] Mỗi RequestId v4 được tạo trước transaction, giữ nguyên khi retry và so khớp payload khi trùng.
- [ ] Hai số dư, hai biến động và chứng từ đều ghi **một read-write transaction**.
- [ ] Có constraint cho positive amount, distinct accounts và số dư không âm.
- [ ] Commit timestamp ở cuối DML transaction, không dùng timestamp làm unique ID.
- [ ] Không có gọi Pub/Sub/HTTP/charge bên trong callback tự retry.
- [ ] Không sửa/xóa history; dùng transfer bù trừ, outbox/change streams cho sự kiện.
- [ ] Có SQL reconciliation, test concurrency, timeout-after-commit và duplicate requests.
- [ ] Runtime IAM ít quyền, FGAC khi cần; quyền đọc theo tenant được enforce tại ứng dụng.
- [ ] Kiểm thử emulator + Spanner staging thực; đo P95 latency, abort/hot rows và chi phí.
- [ ] Có backup/PITR, logging/audit, runbook và kế hoạch canary/rollback.

## 14. Bài tập vận dụng

**Bài 1 — Invariant.** A có 150,00 USD, B có 20,00 USD. Chuyển 45,75 USD. Viết hai `DeltaMinor` theo cents, số dư mới và SQL kiểm tra tổng biến động bằng 0. Vì sao ghi A/B bằng hai transactions riêng là sai?

**Bài 2 — Idempotency.** Client gửi RequestId `R` để chuyển 2500 cents, nhận timeout rồi gửi lại cùng ID. Trình bày phản hồi khi (a) transaction đã commit; (b) chưa commit; (c) payload của lần retry đổi thành 3500 cents.

**Bài 3 — Đồng thời.** A còn 6.000 cents. Hai request khác ID đồng thời muốn chuyển 4.000 cents tới hai người nhận. Với serializable transaction, mô tả tối đa bao nhiêu request có thể thành công và vai trò của `ABORTED`/retry.

**Bài 4 — Thiết kế schema.** Vì sao `PRIMARY KEY (PostedAt, RequestId)` là lựa chọn xấu ở tải ghi cao? Hãy thay bằng UUID v4, giải thích chi phí secondary index và đọc lịch sử theo AccountId.

**Bài 5 — Kiểm tra SQL.** Tạo một bản dữ liệu kiểm thử có Transfers một dòng nhưng LedgerEntries một dòng; dự đoán output của query reconciliation. Bổ sung query tìm sai tenant/currency giữa entries và transfer.

**Bài 6 — Sửa sai.** Một giao dịch đã post 500 cents nhưng nghiệp vụ yêu cầu hoàn lại. Vì sao không `UPDATE LedgerEntries`? Hãy tạo thiết kế transfer đảo chiều tham chiếu RequestId cũ và quy tắc để không hoàn tiền hai lần.

**Bài 7 — Java.** Tìm vị trí có thể phát sinh overflow, thiếu tiền hoặc idempotency-key conflict trong `LedgerDemo`. Viết unit/integration tests cho từng trường hợp và xác minh không phát sinh partial writes.

**Bài 8 — Sự kiện ngoài Spanner.** Sau khi post transfer, ứng dụng cần publish Pub/Sub. Vẽ hai lỗi “DB commit rồi publish fail” và “publish rồi DB rollback”; đề xuất transactional outbox/change streams và consumer idempotency.

**Bài 9 — Quyền và độ tin cậy.** Java service chạy Cloud Run, reconciliation job chạy GKE, DB ở project dữ liệu. Hãy chỉ ra danh tính runtime và IAM riêng, cách chặn truy vấn đọc chéo tenant, hai metrics cần alert và ảnh hưởng của việc tạo mới Spanner client mỗi request.

**Bài 10 — Migration.** Hệ thống cũ có account balances nhưng không có toàn bộ ledger entries lịch sử. Thiết kế snapshot/opening balance được kiểm toán, mốc đối soát, import kiểm tra tổng, khả năng rollback, và điều kiện trước khi chuyển lưu lượng thật sang Spanner.

## Tài liệu tham khảo chính thức

- [Spanner overview](https://cloud.google.com/spanner/docs/overview) — kiến trúc database phân tán và consistency.
- [Transactions overview](https://cloud.google.com/spanner/docs/transactions) — read-write, serializability và commit.
- [Get started with Spanner in Java](https://cloud.google.com/spanner/docs/getting-started/java) — `DatabaseClient`, DML, transactions và queries.
- [Spanner Java TransactionRunner](https://cloud.google.com/java/docs/reference/google-cloud-spanner/latest/com.google.cloud.spanner.TransactionRunner) — retry tự động và commit timestamp.
- [DML best practices](https://cloud.google.com/spanner/docs/dml-best-practices) — DML vs mutations và commit timestamps.
- [Commit timestamps](https://cloud.google.com/spanner/docs/commit-timestamp) — `PENDING_COMMIT_TIMESTAMP()`.
- [Schema design best practices](https://cloud.google.com/spanner/docs/schema-design) — UUID v4, key range hotspots và secondary index.
- [Create/check constraints](https://cloud.google.com/spanner/docs/check-constraint/how-to) — CHECK trên dữ liệu cùng bảng.
- [Create database with Google Cloud CLI](https://cloud.google.com/spanner/docs/getting-started/gcloud) — instance, database và schema.
- [Spanner emulator](https://cloud.google.com/spanner/docs/emulator) — local tests và khác biệt production.
- [Spanner IAM roles](https://cloud.google.com/spanner/docs/iam) — permissions theo database và fine-grained access.
- [Spanner change streams](https://cloud.google.com/spanner/docs/change-streams) — phát hiện thay đổi đã commit.
- [Spanner Query insights](https://cloud.google.com/spanner/docs/query-insights) và [Key Visualizer](https://cloud.google.com/spanner/docs/key-visualizer) — quan sát slow queries/hotspots.
- [Backup and recovery](https://cloud.google.com/spanner/docs/backup) — backup/restore.
- [Spanner pricing](https://cloud.google.com/spanner/pricing) — compute, storage và cấu hình vùng/edition.
