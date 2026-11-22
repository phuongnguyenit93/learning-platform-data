# Định danh duy nhất, ràng buộc dữ liệu và xử lý tên tài khoản trùng

Trong hệ thống Spring Security Authentication, **xác thực thành công phải dẫn đến một danh tính được xác định rõ ràng**, chứ không phải “lấy đại bản ghi đầu tiên có tên gần giống”. Nếu hai account được phép có cùng username mà chương trình không quy định phạm vi phân biệt, việc tìm tài khoản để kiểm tra password, gắn principal và kiểm tra quyền trở nên mơ hồ. Nếu chỉ kiểm tra trùng bằng câu lệnh `SELECT` rồi mới `INSERT`, hai request đồng thời vẫn có thể tạo bản ghi trùng nếu database không thực thi ràng buộc tương ứng.

Bài này thuộc nhóm **Kho tài khoản** của Spring Security Authentication. Trọng tâm là **định danh nội bộ duy nhất và ổn định, khóa đăng nhập có quy tắc chuẩn hóa nhất quán, unique constraint/index ở database, cách xử lý tên tài khoản trùng khi đăng ký/đổi tên, an toàn đồng thời, cùng ranh giới giữa account repository và `UserDetailsService`**.

**Kết luận trước:** Hãy tách **`accountId`** dùng làm danh tính bền vững khỏi **`loginName`** người dùng nhập; xác định tên đăng nhập phải duy nhất *trong phạm vi nào*; lưu một **`loginKey` chuẩn hóa**; và để **database** bảo đảm tính duy nhất cuối cùng. Validation ở ứng dụng chỉ nhằm phản hồi dễ hiểu, không thay thế constraint.

## 1. Ba loại định danh không được đánh đồng

Một account có thể có nhiều dạng định danh:

| Thành phần | Ví dụ | Hợp đồng | Có nên dùng làm khóa ngoại? |
|---|---|---|---|
| **Internal account ID** | UUID `1a...` | Duy nhất, ổn định, thuộc sở hữu hệ thống | **Có**, ưu tiên cho dữ liệu nghiệp vụ và audit |
| **Login name / username** | `linh`, `Linh`, `linh@company.example` | Do người dùng nhập hoặc được quản lý; có thể được đổi | Thường **không**; là alias/credential identifier |
| **Canonical login key** | `linh` | Giá trị chuẩn hóa để tra cứu và áp dụng uniqueness | Dùng cho lookup; không thay `accountId` làm khóa chính |
| **External identity key** | `(issuer, subject)` từ OIDC | Nhận diện bên ngoài theo nhà cung cấp danh tính | Liên kết qua bảng mapping sang `accountId` |
| **Display name** | `Linh Nguyễn` | Nội dung hiển thị, có thể trùng tùy ý | **Không**; không phải yếu tố xác thực |

Ví dụ hai người có cùng tên hiển thị `"Nguyễn Văn An"` là hoàn toàn bình thường. Nhưng nếu chính sách login là “username duy nhất trong mỗi tổ chức”, hai account trong cùng tổ chức không thể có cùng **canonical login key**. Hai tổ chức khác nhau có thể đều có username `"an"` nếu login flow biết đang xác thực trong tổ chức nào.

### 1.1. Vì sao accountId phải ổn định?

Các bảng như `orders.created_by_account_id`, `project_memberships.account_id`, `audit_logs.actor_account_id` nên tham chiếu account bằng ID nội bộ, không bằng email/username. Nếu người dùng đổi `linh` thành `linh.nguyen`, lịch sử đơn hàng, quyền và audit vẫn trỏ tới **cùng account**.

ID ổn định không có nghĩa có thể bỏ qua an toàn: UUID khó đoán cũng không phải authorization. API `GET /accounts/{id}` vẫn phải kiểm tra người gọi có quyền xem account đó không. Khi account bị đóng/xóa dữ liệu cá nhân, cần quy định retention/soft delete và cách audit giữ tham chiếu theo chính sách.

### 1.2. “Duy nhất” luôn có phạm vi

Có hai mô hình chính:

- **Global username:** mỗi `loginKey` được dùng tối đa một lần trong toàn hệ thống. Tra cứu login có thể chỉ theo key.
- **Tenant-scoped username:** mỗi cặp `(tenantId, loginKey)` duy nhất. `linh` ở công ty A và `linh` ở công ty B là hai account khác nhau.

Đừng dùng global unique nếu nghiệp vụ cố ý cho tên trùng giữa các tenant; cũng đừng dùng tenant-scoped unique khi form login chỉ nhận username/password mà **không có cách chọn tenant đáng tin**, vì hệ thống không thể tự xác định đang tìm account nào. Tùy sản phẩm, người dùng chọn tổ chức, URL/subdomain xác định tenant, hay một identity broker thực hiện khám phá tài khoản trước khi xác thực; mỗi phương án cần kiểm tra quyền và chống dò tài khoản.

Một account có thể hoạt động ở nhiều tenant thông qua bảng membership. Trong trường hợp đó, **identity toàn cục**, **login identifier**, **membership theo tenant** và **authorization theo tenant** là các đối tượng khác nhau; không ép mọi hệ thống vào mô hình một account = một tenant.

## 2. Chuẩn hóa tên đăng nhập: hai chuỗi nhìn giống nhau có thật sự trùng?

Định danh do người dùng nhập thường có khác biệt về chữ hoa/thường, khoảng trắng và Unicode:

~~~text
Alice
alice
  ALICE
Ａｌｉｃｅ  (chữ dạng fullwidth Unicode)
A\u0301lice (Unicode tổ hợp; chỉ để minh họa điểm cần quy định)
~~~

Không có một phép `toLowerCase()` nào là đáp án đúng cho mọi locale, mọi tên người và mọi username. Phải **chọn chính sách định danh trước**, rồi áp dụng nhất quán khi đăng ký, đổi tên, login, import dữ liệu và migration.

### 2.1. Ví dụ chính sách username ASCII đơn giản

Để dễ kiểm thử và tránh nhiều vấn đề Unicode trong ví dụ Java 17 bên dưới, ta chọn chính sách **minh họa**:

1. Bỏ khoảng trắng đầu/cuối với `String.strip()`.
2. Chuyển chữ cái Latin ASCII sang chữ thường bằng `toLowerCase(Locale.ROOT)`.
3. Cho phép **chỉ** các ký tự `a-z`, `0-9`, dấu chấm, gạch dưới, gạch ngang, tổng độ dài 3–32.
4. Lưu `loginName` để hiển thị (bản đã strip) và `loginKey` để tra cứu/đảm bảo unique.

Theo chính sách đó:

| Người dùng nhập | loginKey | Kết quả |
|---|---|---|
| `Alice` | `alice` | Hợp lệ |
| `  ALICE  ` | `alice` | Trùng `Alice` trong cùng namespace |
| `a.li_ce-2` | `a.li_ce-2` | Hợp lệ |
| `Álice` | — | Bị từ chối vì ngoài tập ký tự đã chọn |
| `ab` | — | Bị từ chối vì quá ngắn |
| `alice@example.com` | — | Bị từ chối vì ví dụ này không cho ký tự `@` |

Nếu sản phẩm **cho đăng nhập bằng email**, hãy thiết kế một canonicalization policy riêng, cân nhắc quy tắc email được chấp nhận và xác minh địa chỉ. Không tùy tiện loại dấu chấm, dấu cộng, phần đuôi sau `+` hoặc coi mọi email có cùng mailbox: điều đó phụ thuộc nhà cung cấp và có thể gộp nhầm tài khoản.

### 2.2. Với Unicode hoặc nhiều ngôn ngữ

Nếu cho username tiếng Việt, Hán tự hoặc các ký tự Unicode khác, cần cân nhắc:

- Chuẩn hóa `NFC` hay `NFKC` theo sản phẩm; NFKC có thể gộp cả các dạng tương thích mà người dùng tưởng là khác nhau.
- Case mapping/case folding và quy tắc locale; `Locale.ROOT` không thay thế hoàn toàn Unicode casefold.
- Các ký tự dễ gây nhầm lẫn bằng hình dạng (confusables), zero-width characters, dấu tổ hợp và độ dài theo code point/grapheme thay vì chỉ `String.length()`.
- Quy tắc collation/index trong database có thực sự giống chính sách ứng dụng không.
- Migration khi chính sách chuẩn hóa thay đổi, vì các loginKey trước đây khác nhau có thể đột nhiên va chạm.

**Không áp dụng hai thuật toán khác nhau** ở register và login. Nếu application lưu key bằng Java nhưng SQL tìm bằng `lower(login_name)` theo collation khác, cùng input có thể dẫn tới lookup sai. Với định danh nhiều ngôn ngữ, hãy test rõ những trường hợp Unicode có nguy cơ hợp nhất hoặc phân tách khác dự định.

## 3. Đặt ràng buộc tại tầng database: ví dụ PostgreSQL

Đây là một schema **minh họa cho PostgreSQL** theo mô hình account thuộc một tenant, username chỉ gồm ASCII và password hash có thể null nếu đăng nhập qua IdP. Sản phẩm thật có thể phải tách account khỏi membership hoặc lưu nhiều login identities.

~~~sql
CREATE TABLE accounts (
    id            UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL,
    login_name    TEXT NOT NULL,
    login_key     TEXT NOT NULL,
    password_hash TEXT,
    status        TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_accounts_login_name_not_blank
        CHECK (btrim(login_name) <> ''),
    CONSTRAINT ck_accounts_login_key
        CHECK (login_key ~ '^[a-z0-9._-]{3,32}$'),
    CONSTRAINT ck_accounts_status
        CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'CLOSED')),
    CONSTRAINT uq_accounts_tenant_login_key
        UNIQUE (tenant_id, login_key),
    CONSTRAINT uq_accounts_tenant_id
        UNIQUE (tenant_id, id)
);
~~~

Giải thích:

- `id`: primary key duy nhất cho mọi account; tạo bởi server hoặc database theo chính sách, không tự tin ID do client gửi.
- `tenant_id`: phạm vi username. Nếu là foreign key đến bảng `tenants`, hãy khai báo FK thực tế trong schema production.
- `login_name`: tên hiển thị/trả về có kiểm soát, không dùng để tìm bằng so sánh mơ hồ.
- `login_key`: normalized key **có cùng logic ở mọi luồng ghi**. DB `CHECK` giới hạn tập ký tự cho ví dụ ASCII; DB không tự suy ra `login_key = normalize(login_name)`. Hãy kiểm soát tính nhất quán bằng service, database-generated expression/trigger phù hợp hoặc cơ chế được kiểm thử.
- `password_hash`: cho phép null nếu account không sử dụng mật khẩu nội bộ; phải có ràng buộc nghiệp vụ bảo đảm account có một phương thức đăng nhập hợp lệ.
- `uq_accounts_tenant_login_key`: chỉ một account cho mỗi cặp `(tenant_id, login_key)`, kể cả khi hai request chạy đồng thời.
- `uq_accounts_tenant_id`: ràng buộc bổ sung để hỗ trợ ví dụ FK tổ hợp ở dưới; nó dư về mặt tính duy nhất vì `id` đã là PK, nhưng có ích khi muốn FK bảo toàn tenant.

PostgreSQL tự tạo unique B-tree index tương ứng với `UNIQUE`; thông thường **không cần tạo thêm một index trùng hệt**. `UNIQUE (tenant_id, login_key)` không bảo đảm username duy nhất toàn cục và cũng không bảo đảm display name duy nhất.

### 3.1. Bảo vệ liên kết tenant trong bảng con

Một bảng membership hoặc tài nguyên cùng tenant có thể sử dụng FK kép:

~~~sql
CREATE TABLE account_audit_refs (
    id         UUID PRIMARY KEY,
    tenant_id  UUID NOT NULL,
    account_id UUID NOT NULL,
    CONSTRAINT fk_audit_account_same_tenant
        FOREIGN KEY (tenant_id, account_id)
        REFERENCES accounts (tenant_id, id)
);
~~~

Vì sao không chỉ FK `account_id`? Với bảng nghiệp vụ có tenant, một lỗi ghi dữ liệu có thể tạo row tuy có `tenant_id = A` nhưng lại trỏ account thuộc `tenant_id = B`. FK kép giúp database ngăn kiểu **cross-tenant reference** này. Nó không thay thế authorization, row-level security hoặc kiểm tra ownership khi đọc/ghi.

### 3.2. CHECK, NOT NULL, UNIQUE, PK, FK giải quyết chuyện khác nhau

| Cơ chế | Ngăn cái gì? | Không tự giải quyết cái gì? |
|---|---|---|
| `PRIMARY KEY` | Hai row cùng account ID; ID null | Username trùng, quyền truy cập |
| `NOT NULL` | Thiếu dữ liệu bắt buộc | Chuỗi rỗng hoặc toàn khoảng trắng |
| `CHECK` | Giá trị ngoài tập/điều kiện quy định | Xung đột với row khác |
| `UNIQUE` / unique index | Trùng khóa trong phạm vi xác định | Chuẩn hóa trước khi ghi, cấp quyền |
| `FOREIGN KEY` | Tham chiếu tới row không tồn tại hoặc sai khóa tổ hợp | Bảo đảm người gọi HTTP được phép xem row |
| Transaction | Tập thay đổi nguyên tử theo cơ chế DB | Unique nếu bạn không tạo constraint/index |

Validation Java là lớp cần thiết để thông báo sớm, nhưng **không phải trọng tài cuối cùng** khi nhiều process ghi cùng database.

### 3.3. Nullable và chính sách email

Trong PostgreSQL, `UNIQUE(email)` theo mặc định thường **cho phép nhiều dòng có email NULL**; các giá trị NULL không bị coi bằng nhau trong kiểm tra unique theo mặc định. PostgreSQL 15+ có cú pháp `UNIQUE NULLS NOT DISTINCT` nếu chính sách cần coi các NULL tương đương. Chọn theo nhu cầu, không dùng như mẹo chung cho mọi database.

Không mặc nhiên đánh dấu `email UNIQUE` nếu nghiệp vụ cho phép nhiều account chia sẻ một địa chỉ liên hệ, hoặc một người có các tài khoản tenant khác nhau. **Email có được xác minh không?** và **email có phải login identifier không?** là các câu hỏi khác nhau. Nếu login bằng email, uniqueness và canonicalization của email phải được xác định theo phạm vi phù hợp.

### 3.4. Khóa identity provider bên ngoài

Với OIDC/OAuth2, subject thường có ý nghĩa trong phạm vi issuer, nên một mô hình mapping có thể là:

~~~sql
CREATE TABLE external_identities (
    id               UUID PRIMARY KEY,
    account_id       UUID NOT NULL REFERENCES accounts(id),
    issuer           TEXT NOT NULL,
    external_subject TEXT NOT NULL,
    CONSTRAINT uq_external_issuer_subject
        UNIQUE (issuer, external_subject)
);
~~~

`(issuer, external_subject)` xác định một external identity đã liên kết, còn `account_id` chỉ tới account nội bộ. Không tự gộp account dựa vào email do IdP cung cấp mà chưa xác minh chính sách link. Nếu có nhiều tenant hoặc nhiều loại identity khác, scope unique cần được xác định trước để không tạo liên kết chéo không mong muốn.

## 4. Tại sao SELECT trước INSERT không chống trùng khi có concurrency?

Một cách viết dễ mắc:

~~~text
Request A: SELECT login_key='linh' -> không thấy
Request B: SELECT login_key='linh' -> không thấy
Request A: INSERT account 'linh'  -> thành công
Request B: INSERT account 'linh'  -> thành công nếu DB không có UNIQUE
~~~

Ngay cả khi bạn dùng:

~~~sql
SELECT 1
FROM accounts
WHERE tenant_id = :tenantId AND login_key = :loginKey;
~~~

trước khi insert, khoảng thời gian giữa **kiểm tra** và **ghi** vẫn là cửa sổ race condition (*time of check/time of use*, TOCTOU). Chỉ kiểm tra tồn tại ở ứng dụng không ngăn request từ nhiều app instances, background jobs hay admin tools ghi trùng.

### 4.1. Unique constraint là điểm phân xử cuối

Khi có constraint `uq_accounts_tenant_login_key`:

~~~text
T0: Request A, B đều hỏi trước và thấy key còn trống.
T1: A INSERT (tenant X, login_key='linh').
T2: B INSERT (tenant X, login_key='linh').
T3: Database đảm bảo không có hai row cùng unique key đã commit.
    - A thắng: B có thể đợi rồi nhận unique violation.
    - A rollback: B có thể tiếp tục tùy transaction/DB.
~~~

Trong PostgreSQL, lỗi trùng unique key có SQLSTATE **`23505`** (`unique_violation`). Tên constraint trong lỗi giúp xác định chính xác key nào bị xung đột; không suy mọi `DataIntegrityViolationException` hoặc mọi lỗi SQL là “username đã tồn tại”.

**Transaction đơn thuần không thay thế unique constraint.** Ngay ở mức isolation thông dụng, hai câu `SELECT` vẫn có thể cùng thấy trống. Biện pháp hiệu quả là tạo constraint/index thể hiện đúng business invariant và xử lý nhánh conflict.

### 4.2. SQL INSERT và xử lý conflict

Insert bình thường:

~~~sql
INSERT INTO accounts (
    id, tenant_id, login_name, login_key, password_hash, status
) VALUES (
    :id, :tenantId, :loginName, :loginKey, :passwordHash, 'ACTIVE'
);
~~~

Tham số `:id` ... ở trên là placeholder của tầng truy cập DB; không chạy trực tiếp trong `psql` nếu chưa bind giá trị. Khi constraint bị vi phạm, rollback giao dịch và phản hồi theo chính sách.

PostgreSQL hỗ trợ một lựa chọn để tránh exception ở trường hợp duplicate **đã dự kiến**:

~~~sql
INSERT INTO accounts (
    id, tenant_id, login_name, login_key, password_hash, status
) VALUES (
    :id, :tenantId, :loginName, :loginKey, :passwordHash, 'ACTIVE'
)
ON CONFLICT ON CONSTRAINT uq_accounts_tenant_login_key
DO NOTHING
RETURNING id;
~~~

Nếu lệnh trả một ID, account mới đã được insert. Nếu trả **0 row**, một account với key đó đã tồn tại/xảy ra conflict; service xử lý đúng tình huống trùng, không tự lấy account có sẵn rồi coi người yêu cầu là chủ sở hữu. Nếu có các constraint khác, lỗi tương ứng vẫn phải được xử lý riêng.

**Cảnh báo:** Tránh một câu `ON CONFLICT DO UPDATE SET password_hash = EXCLUDED.password_hash` trên endpoint đăng ký. Nó có thể cho phép người chưa được xác minh đổi credential hoặc chiếm account đang tồn tại. “Đăng ký trùng” không bao giờ là lý do để tự thay password, quyền, email xác minh hoặc chủ sở hữu của bản ghi cũ.

### 4.3. Phản hồi HTTP phù hợp và account enumeration

Đối với một API đăng ký username công khai, `409 Conflict` có thể là lựa chọn hợp lý về mặt REST khi resource name bị trùng; tuy nhiên, **chính phản hồi 409 khác biệt cũng có thể giúp dò tài khoản**. Chính sách công khai phải cân bằng nhu cầu UX và chống account enumeration:

- Với tên người dùng công khai vốn được phép tra cứu, có thể thông báo tên không khả dụng sau rate limit và kiểm soát tải.
- Với email/login identifier riêng tư, cân nhắc thông báo chung, quy trình xác minh email và không tiết lộ account tồn tại ở mọi endpoint.
- Dù phản hồi thế nào, backend vẫn phải không tạo account trùng hoặc chuyển giao quyền trên account hiện có.

Không trả nguyên tên index, SQLSTATE, stacktrace hoặc password hash cho client. Ở server, ghi correlation ID và error code đủ để chẩn đoán, không log raw password.

## 5. Ví dụ Java 17 chạy độc lập: canonical key, tenant scope và race

Ví dụ dưới dùng **JDK 17 thuần**, không phụ thuộc Spring Boot, để minh họa một invariant có thể kiểm chứng:

- Cặp `(tenantId, loginKey)` duy nhất.
- `Alice` và `  ALICE  ` trùng trong một tenant.
- Cùng loginKey ở tenant khác được phép theo policy.
- Hai thread đồng thời tạo `bob` thì chỉ có một thread thành công.
- `accountId` được tạo riêng và dùng làm ID ổn định.

**Quan trọng:** `ConcurrentHashMap.putIfAbsent` trong ví dụ chỉ là cơ chế atomic **trong một tiến trình JVM**. Nó không thay unique constraint trong database khi nhiều service instances cùng ghi. Ở production, database phải là nguồn sự thật.

### 5.1. Cấu trúc và tệp Java

~~~text
account-name-demo/
└── src/example/AccountNameDemo.java
~~~

Tạo `src/example/AccountNameDemo.java`:

~~~java
package example;

import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class AccountNameDemo {

    record ScopedKey(UUID tenantId, String loginKey) {}

    record Account(UUID id, UUID tenantId,
                   String loginName, String loginKey) {}

    static final class DuplicateNameException
            extends RuntimeException {
        DuplicateNameException() {
            super("Login name already exists");
        }
    }

    static String normalize(String input) {
        Objects.requireNonNull(input, "loginName");
        String key = input.strip().toLowerCase(Locale.ROOT);
        if (!key.matches("[a-z0-9._-]{3,32}")) {
            throw new IllegalArgumentException("Invalid login name");
        }
        return key;
    }

    static final class AccountStore {
        private final ConcurrentMap<ScopedKey, Account> rows =
                new ConcurrentHashMap<>();

        Account create(UUID tenantId, String rawLoginName) {
            Objects.requireNonNull(tenantId, "tenantId");
            String key = normalize(rawLoginName);
            Account proposed = new Account(
                    UUID.randomUUID(), tenantId,
                    rawLoginName.strip(), key);
            ScopedKey scoped = new ScopedKey(tenantId, key);

            if (rows.putIfAbsent(scoped, proposed) != null) {
                throw new DuplicateNameException();
            }
            return proposed;
        }

        Optional<Account> find(UUID tenantId, String rawLoginName) {
            Objects.requireNonNull(tenantId, "tenantId");
            return Optional.ofNullable(rows.get(
                    new ScopedKey(tenantId, normalize(rawLoginName))));
        }
    }

    public static void main(String[] args) throws Exception {
        UUID tenantA = UUID.fromString(
                "00000000-0000-0000-0000-00000000000a");
        UUID tenantB = UUID.fromString(
                "00000000-0000-0000-0000-00000000000b");
        AccountStore store = new AccountStore();

        Account alice = store.create(tenantA, "Alice");
        System.out.println("A/Alice -> CREATED");

        try {
            store.create(tenantA, "  ALICE  ");
        } catch (DuplicateNameException ex) {
            System.out.println("A/ALICE -> DUPLICATE");
        }

        store.create(tenantB, "alice");
        System.out.println("B/alice -> CREATED");

        boolean found = store.find(tenantA, "aLiCe").isPresent();
        System.out.println("A/aLiCe found -> " + found);

        UUID lookedUpId = store.find(tenantA, "ALICE")
                .orElseThrow().id();
        System.out.println("stable account ID -> "
                + alice.id().equals(lookedUpId));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);

        Callable<Boolean> createBob = () -> {
            go.await();
            try {
                store.create(tenantA, "bob");
                return true;
            } catch (DuplicateNameException ex) {
                return false;
            }
        };

        Future<Boolean> first = pool.submit(createBob);
        Future<Boolean> second = pool.submit(createBob);
        go.countDown();

        int created = (first.get() ? 1 : 0)
                    + (second.get() ? 1 : 0);
        pool.shutdown();
        System.out.println("concurrent bob -> created=" + created
                + ", duplicate=" + (2 - created));
    }
}
~~~

Mã dùng `Locale.ROOT` cho quy tắc key ASCII cụ thể, `UUID.randomUUID()` cho khóa nội bộ, `ScopedKey` làm composite map key, và `putIfAbsent` để quyết định atomic trong JVM. Thứ tự thread thắng không định trước, nhưng **số lượng tạo thành công** là deterministic vì map chỉ giữ một entry trên cùng key.

### 5.2. Biên dịch, chạy và stdout

Từ thư mục `account-name-demo` có JDK 17+:

~~~bash
javac -encoding UTF-8 -d out src/example/AccountNameDemo.java
java -cp out example.AccountNameDemo
~~~

Đầu ra mong đợi:

~~~text
A/Alice -> CREATED
A/ALICE -> DUPLICATE
B/alice -> CREATED
A/aLiCe found -> true
stable account ID -> true
concurrent bob -> created=1, duplicate=1
~~~

Thử đổi `store.create(tenantA, "bob")` trong task thành các biến thể `"Bob"` và `" bOb "`: kết quả vẫn chỉ có một account vì normalize ra cùng `"bob"`. Thử tạo `"ab"` hoặc `"linh@example.com"`: chương trình ném `IllegalArgumentException` theo rule ví dụ. Nếu nghiệp vụ cho phép ký tự khác, thay policy một cách nhất quán ở mọi tầng, không chỉ sửa regex.

### 5.3. Giới hạn của demo cần nắm

- `ConcurrentHashMap` chỉ bảo vệ trong một process. Hai pod khác nhau có map riêng vẫn có thể cùng tạo username; DB unique constraint mới bảo vệ invariant toàn hệ thống.
- Không có hash mật khẩu hay Spring Security filter vì ví dụ này tập trung **định danh và uniqueness**, không trình diễn login.
- Không có đổi tên, xóa account hoặc giao dịch nhiều bảng. Đó là các thao tác phải thiết kế atomic trên database.
- `UUID.randomUUID()` tạo ID không có ý nghĩa phân quyền; đừng tiết lộ hoặc nhận ID từ client mà bỏ qua authorization.
- Output không in UUID để cố định stdout giữa các lần chạy. Không có bước nào phụ thuộc số lượng hoặc thứ tự thread thắng.

## 6. Kết nối với Spring Security: tra đúng một UserDetails

`UserDetailsService` có hợp đồng:

~~~java
UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException;
~~~

Nó là contract tải dữ liệu xác thực theo username cho những provider như `DaoAuthenticationProvider`; **không tự kiểm tra mật khẩu** và không quyết định quyền truy cập tài nguyên. Đường đi:

~~~text
Login request
  -> username được chuẩn hóa theo policy
  -> UserDetailsService / AccountRepository
  -> Tra cứu đúng namespace + canonical login key
  -> 0 row: UsernameNotFoundException
  -> 1 row: UserDetails chứa password hash/flags/authorities tin cậy
  -> Nếu >1 row: lỗi toàn vẹn dữ liệu; không chọn row đầu tiên
  -> DaoAuthenticationProvider kiểm tra password/status
  -> Authentication result với principal đã xác thực
~~~

Một triển khai **minh họa cho ứng dụng chỉ có một namespace login toàn cục**:

~~~java
@Service
public class AccountUserDetailsService implements UserDetailsService {

    private final AccountRepository repository;

    public AccountUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        String loginKey = LoginNames.normalize(username);
        AccountEntity account = repository.findByLoginKey(loginKey)
                .orElseThrow(() ->
                        new UsernameNotFoundException("Invalid credentials"));

        return User.withUsername(account.getLoginName())
                .password(account.getPasswordHash())
                .authorities(account.getGrantedAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .build();
    }
}
~~~

**Đây là đoạn tích hợp, không phải chương trình Java độc lập.** Cần có imports Spring, `AccountRepository`, `AccountEntity`, `LoginNames`, mapping authorities và trạng thái. `User.withUsername(...).password(...)` chỉ phù hợp khi account có phương thức login bằng password. Nếu account chỉ dùng OIDC, hãy sử dụng provider tương ứng thay vì đưa password hash giả vào account.

**Với schema `UNIQUE(tenant_id, login_key)` ở mục 3, không được dùng nguyên `findByLoginKey(loginKey)`** vì một loginKey có thể tồn tại ở nhiều tenant. Cần chuyển cả **tenant context đã được xác lập đúng theo flow đăng nhập** vào repository (ví dụ `findByTenantIdAndLoginKey(tenantId, key)`) và cấu hình authentication pipeline/provider phù hợp. Không đơn giản lấy tenant ID từ request body rồi coi là quyền đã được chứng minh.

### 6.1. Nếu database đã có username trùng từ dữ liệu cũ

Một anti-pattern nghiêm trọng:

~~~java
return repository.findFirstByLoginKey(loginKey).orElseThrow(...);
~~~

Nếu database có hai bản ghi trùng key, truy vấn “first” có thể trả account sai hoặc thay đổi theo kế hoạch thực thi SQL, dẫn đến principal và dữ liệu nghiệp vụ của người khác bị dùng nhầm. **Không dùng `findFirst` như biện pháp chữa duplicate identity.** Phải phát hiện conflict, không cấp authentication cho danh tính mơ hồ, sửa dữ liệu và bổ sung ràng buộc phù hợp. Không gộp hai account tự động nếu còn quan hệ dữ liệu, credential hoặc lịch sử khác nhau.

### 6.2. Spring Data/JPA và tên constraint

Trong Spring Data JPA, ví dụ repository:

~~~java
interface AccountRepository extends JpaRepository<AccountEntity, UUID> {
    Optional<AccountEntity> findByTenantIdAndLoginKey(
            UUID tenantId, String loginKey);
}
~~~

Đây là **đoạn định nghĩa repository**, cần `AccountEntity` có đúng property names và imports tương ứng. Trong ứng dụng Spring, việc khai báo `@Column(unique = true)` cho mỗi cột `tenantId` và `loginKey` **không tương đương** composite unique `(tenantId, loginKey)`; làm như vậy có thể cấm hai tenant dùng cùng loginKey. Dùng migration DDL rõ ràng (Flyway/Liquibase) hoặc `@Table(uniqueConstraints = ...)` đúng cặp cột và xác minh schema thực tế.

Không dùng `ddl-auto=update` như thay thế quy trình migration có kiểm tra trên production. Quan trọng hơn là DB hiện có constraint đúng và dữ liệu cũ đã được làm sạch.

## 7. Đăng ký và đổi tên trong Spring: xử lý cạnh tranh đúng chỗ

Luồng đăng ký an toàn ở mức nghiệp vụ:

~~~text
Input registration (tenant, username, password...)
   |
   +--> Validate format / normalize -> loginKey
   +--> Tùy chọn check tồn tại để hỗ trợ UX, không dựa vào đó làm khóa
   +--> Hash password / xác minh điều kiện đăng ký
   |
   v
Transaction: INSERT account với ID mới
   |
   +--> Thành công -> commit -> phát event nghiệp vụ thích hợp
   |
   '--> Vi phạm UNIQUE -> rollback -> xử lý duplicate theo policy
~~~

### 7.1. Đoạn service minh họa

~~~java
@Service
public class RegistrationService {
    private final AccountRepository accounts;
    private final PasswordEncoder encoder;

    public RegistrationService(AccountRepository accounts,
                               PasswordEncoder encoder) {
        this.accounts = accounts;
        this.encoder = encoder;
    }

    @Transactional
    public UUID register(UUID tenantId, String loginName,
                         String rawPassword) {
        String key = LoginNames.normalize(loginName);
        AccountEntity entity = new AccountEntity(
                UUID.randomUUID(), tenantId, loginName.strip(), key,
                encoder.encode(rawPassword));
        // saveAndFlush giúp lỗi constraint thường xuất hiện tại đây.
        return accounts.saveAndFlush(entity).getId();
    }
}
~~~

**Đoạn này không phải file runnable độc lập**: `AccountEntity` constructor, bean, imports và các ràng buộc khác thuộc dự án thật; validation password/tenant và chính sách đăng ký cần được bổ sung. Giả định một transaction được kích hoạt qua Spring proxy đúng cấu hình. `saveAndFlush` giúp lỗi constraint xuất hiện sớm hơn, **không thay transaction commit** hoặc mọi kiểm tra DB trì hoãn đến commit.

Cách xử lý duplicate phải nằm ở boundary thích hợp:

- Nếu xảy ra `DataIntegrityViolationException`, kiểm tra nguyên nhân/constraint **được xác định chắc chắn** (`uq_accounts_tenant_login_key` hoặc SQLSTATE tương ứng), sau đó chuyển thành lỗi miền “login name conflict”.
- **Không coi mọi `DataIntegrityViolationException` đều là trùng username**: có thể là FK, check, null, một unique khác hoặc lỗi schema.
- Trong PostgreSQL, sau một SQL error làm transaction rơi vào trạng thái aborted, không tiếp tục query trong **cùng transaction** như thể chưa có lỗi. Để transaction rollback rồi xử lý response ngoài boundary; hoặc dùng SQL `ON CONFLICT` với semantics được thiết kế.
- Không retry mù quáng với cùng username ở nhiều request: retry khi constraint đã xác định trùng sẽ chỉ lặp lỗi; chỉ retry nếu logic thực sự cấp identifier mới theo chính sách và có giới hạn.
- Khi commit thành công, đừng tự động đăng nhập cho client trước khi đã hoàn tất các yêu cầu xác minh email/MFA/chính sách account.

### 7.2. Đổi username phải giữ account ID

Thao tác đổi tên nên xử lý trong một giao dịch:

1. Xác thực actor; xác minh chủ sở hữu account hoặc quyền admin rõ ràng.
2. Chuẩn hóa tên mới, kiểm tra định dạng và namespace.
3. Cập nhật `login_name` và `login_key` trên **cùng accountId**.
4. Nếu unique conflict, rollback; **không** xóa account hoặc tự đổi tên account đang chiếm key.
5. Khi đổi thành công, đồng bộ cache, audit event, session/JWT/login alias nếu chính sách yêu cầu.

Không cập nhật khóa ngoại của order chỉ vì username đổi. Với principal chứa username snapshot, cần tính cách refresh các tên có thể đã cũ; principal có ID ổn định tránh gãy quan hệ.

### 7.3. Tên cũ được tái sử dụng hay giữ lại?

Một sản phẩm có thể cho phép username cũ được người khác đăng ký sau khi đổi tên hoặc đóng account; sản phẩm khác giữ tên cũ vĩnh viễn để chống mạo danh, confusion hoặc account takeover. Đây là **business policy**, không phải quyết định mặc định của Spring Security.

Có thể tạo bảng `reserved_login_names` với scope, canonical key, reason và timestamp; hoặc dùng unique index có điều kiện trên account active. Nhưng cần biết: tái sử dụng tên cũ có thể làm link, mention, username trong email hay account recovery trỏ sai người. Luôn dùng accountId cho liên kết nội bộ.

## 8. Soft delete và partial unique index: quyết định khó

Nếu row account có `deleted_at` hoặc `status='CLOSED'`, yêu cầu “username chỉ cần duy nhất với account còn hoạt động” có thể được thể hiện bằng **partial unique index** trong PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_accounts_active_login
ON accounts (tenant_id, login_key)
WHERE deleted_at IS NULL;
~~~

Đây là **biến thể schema**, yêu cầu bảng có cột `deleted_at` và phải điều chỉnh/bỏ unique constraint toàn phần `uq_accounts_tenant_login_key` ở ví dụ trước. Nếu vẫn giữ unique constraint toàn phần thì partial index **không** cho phép tái sử dụng tên cũ.

Lựa chọn này có rủi ro đáng kể:

- Hai row khác nhau có thể cùng key, một đã đóng và một active; lookup login phải **lọc chính xác trạng thái** và namespace.
- Khi restore một account bị soft-delete, unique conflict có thể xuất hiện nếu key đã được tái sử dụng.
- Không lấy “row đầu tiên” khi bỏ lọc trạng thái; phải query đúng domain policy.
- Các hệ thống gửi email/thông báo theo username cũ, audit trail và link ngoài cần quy tắc chuyển hướng, tránh lộ dữ liệu của account đã đóng.
- Cần migration và test riêng trước khi đổi policy từ “không tái sử dụng” sang “được tái sử dụng”.

**Không bật partial unique chỉ vì muốn dọn dữ liệu trùng cho dễ.** Phạm vi unique phải phản ánh quy tắc sản phẩm và bảo mật.

## 9. Dọn dữ liệu cũ trước khi tạo UNIQUE constraint

Nếu database đã có account cũ, việc thêm unique constraint có thể thất bại do dữ liệu trùng. Hãy thực hiện migration có kế hoạch:

1. **Chốt chính sách:** global hay tenant-scoped, canonicalization, có tái sử dụng tên sau đóng account không.
2. **Backfill loginKey:** chạy cùng thuật toán chuẩn hóa với ứng dụng, không dùng biến thể SQL khác ngầm về Unicode/case.
3. **Tìm collision:** nhóm theo scope + canonical key; báo những group có hơn một row.
4. **Phân loại:** lỗi nhập liệu, hai người thật khác nhau, duplicate import, liên kết IdP nhầm, account cũ soft-deleted.
5. **Quyết định thủ công có audit:** đổi tên account phù hợp, liên hệ người dùng khi cần; không gộp mật khẩu/quyền/dữ liệu của hai người chỉ vì loginKey giống nhau.
6. **Ngăn ghi trùng trong thời gian migration:** phối hợp dừng ghi hoặc cơ chế dual-write/constraint thay thế được thiết kế; tạo unique constraint khi dữ liệu sạch.
7. **Triển khai atomically với kế hoạch rollback:** kiểm thử app version cũ/mới, cache, registration, login, rename, restore.
8. **Đo hậu triển khai:** số unique conflicts, số login không tìm thấy, số account trùng không mong đợi, thời gian query và cảnh báo dữ liệu.

Một query rà soát **gần đúng cho chính sách tên ASCII** của ví dụ:

~~~sql
SELECT tenant_id,
       lower(btrim(login_name)) AS candidate_key,
       count(*) AS duplicates
FROM accounts
GROUP BY tenant_id, lower(btrim(login_name))
HAVING count(*) > 1;
~~~

`lower(btrim(...))` chỉ để thăm dò ở đây; nó **không được coi tương đương vô điều kiện** với `String.strip().toLowerCase(Locale.ROOT)` khi có Unicode/collation hoặc ký tự ngoài tập ASCII. Migration production nên tính `login_key` bằng cùng policy đã xác nhận, sau đó nhóm trên cột chính thức.

Cần kiểm tra thêm **ID trùng, email/phone policies, external identity mapping, tenant ID sai, orphaned foreign keys**. Không đổi ID các account để “hết trùng username”: ID là danh tính bền vững, tên đăng nhập là alias có thể điều chỉnh theo chính sách.

## 10. Lỗi thường gặp và cách sửa

| Lỗi | Tác hại | Cách khắc phục |
|---|---|---|
| Dùng username/email làm primary key mọi bảng | Đổi tên phá quan hệ/audit | Dùng accountId bất biến |
| `findFirstByLoginName` khi dữ liệu có thể trùng | Có thể đăng nhập nhầm account | Ràng buộc unique đúng scope, query nhận 0/1 row |
| Chỉ `existsByLoginName` rồi `save` | Race giữa hai request/pod | DB unique constraint + xử lý conflict |
| Dùng unique global trong ứng dụng tenant-scoped | Chặn nhầm username ở tenant khác | Unique tổ hợp `(tenantId, loginKey)` |
| Dùng unique tenant-scoped nhưng login chỉ có username | Lookup mơ hồ giữa tenant | Thiết kế identity discovery/tenant selection đáng tin |
| Register lower-case, login query tên gốc | Cùng username được tìm khác nhau | Dùng cùng canonicalization và cột loginKey |
| Normalize Unicode tùy tiện | Gộp nhầm tài khoản hoặc tạo alias gây nhầm | Định nghĩa policy, threat model, test Unicode |
| `@Column(unique=true)` trên cả hai cột | Tạo hai unique riêng, sai nghiệp vụ | Unique composite |
| Bắt mọi lỗi DB thành “username trùng” | Che FK/DB outage/check constraint | Phân loại bằng constraint/SQLSTATE đáng tin |
| `ON CONFLICT DO UPDATE` tự thay password | Nguy cơ account takeover | Với registration duplicate, không sửa account cũ |
| Soft-delete không điều chỉnh unique/lookup | Restore/login sai, tái sử dụng tên bất ngờ | Policy recycle rõ; partial index và query tương thích |
| Trả SQL error cho client | Lộ schema, dữ liệu nhạy cảm | Phản hồi public được kiểm soát, audit nội bộ |
| Đổi tên bằng tạo account mới | Mất ownership/quan hệ lịch sử | UPDATE theo stable ID, giữ audit |
| Dùng UUID khó đoán làm bằng chứng quyền | IDOR và lộ dữ liệu | Kiểm tra authorization trên mỗi tài nguyên |
| Đồng bộ cache chậm sau rename/lock | Principal hoặc quyền cũ tồn tại | Cache/session/token invalidation theo SLA bảo mật |

## 11. Bộ kiểm thử khuyến nghị

Nên kiểm thử ở **hai tầng**: unit test canonicalization và integration test với **database thật cùng loại production**. H2/InMemory Map có thể minh họa logic nhưng khác PostgreSQL về collation, transaction, partial index, SQLSTATE và concurrency; không dùng thay cho bài test unique quan trọng.

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Register `Alice`, sau đó `ALICE` cùng tenant | Lần hai bị duplicate nếu policy ignore case |
| Register `Alice` ở tenant A và tenant B | Được phép nếu policy tenant-scoped |
| Lookup user sau normalize | Trả **một** account đúng scope |
| Username quá ngắn, ký tự ngoài policy | Bị validation từ chối, DB cũng không nhận loginKey ngoài rule |
| Hai transaction insert cùng loginKey đồng thời | Tối đa một row commit thành công |
| Retry request sau network failure | Không tự tạo account thứ hai; có chiến lược idempotency thích hợp |
| DB ném lỗi FK/check khác unique | Không bị gán nhầm thành username duplicate |
| Chuyển tenantId trong lookup | Không đọc/cấp principal của tenant khác |
| Đổi username | Account ID và foreign keys vẫn nguyên |
| Đổi sang username đã bị chiếm | Rollback, cả tên cũ và dữ liệu nghiệp vụ giữ nguyên |
| Soft delete / restore | Tôn trọng chính sách tái sử dụng tên và index tương ứng |
| Dữ liệu migration có collision | Phát hiện, không chọn random account |
| Hai external IdP có cùng `sub` | Mapping theo issuer + subject không va nhau |
| Hai account gắn một external identity | Unique constraint chặn link trùng khi policy không cho phép |
| Đăng nhập sau account bị khóa | Không cấp authentication bất chấp có account row |
| Client cung cấp accountId của người khác | Không chiếm danh tính vì server xác minh actor/authorization |
| Registration trả conflict ra public | Không làm rò thông tin ngoài chính sách cho phép |

### 11.1. Tình huống tự đánh giá

**Câu 1.** Có hai người trong hai công ty cùng username `linh`. Dùng `UNIQUE(login_key)` có đúng không?  
**Đáp án:** Không nếu policy cho tên trùng theo tenant; nên dùng `UNIQUE(tenant_id,login_key)` và login flow phải biết tenant đáng tin.

**Câu 2.** Service gọi `existsByLoginKey` trước `save`, vì sao vẫn có trùng?  
**Đáp án:** Hai request có thể cùng thấy tên chưa tồn tại. DB unique constraint/unique index mới bảo đảm chống trùng khi ghi đồng thời.

**Câu 3.** Username đổi từ `Alice` thành `alice.new`, có nên thay khóa ngoại trong các bảng order không?  
**Đáp án:** Không nếu chúng tham chiếu `accountId` ổn định. Đổi alias không tạo danh tính mới.

**Câu 4.** Vì sao `UserDetailsService.findFirstByLoginName` nguy hiểm khi DB đã có duplicate?  
**Đáp án:** Nó giấu sự mơ hồ, có thể đưa principal/credential của bản ghi không phải người được yêu cầu; cần fail closed và sửa dữ liệu.

**Câu 5.** Có nên cho đăng ký trùng tự cập nhật password hash qua `ON CONFLICT DO UPDATE`?  
**Đáp án:** Không. Người chưa chứng minh sở hữu account có thể thay credentials account đang tồn tại.

**Câu 6.** Dùng `UNIQUE(email)` có chặn mọi email NULL trùng trong PostgreSQL không?  
**Đáp án:** Không theo mặc định. Cần hiểu semantics NULL và chính sách nullable, không tự suy luận từ tên constraint.

**Câu 7.** Tạo unique index chỉ với `deleted_at IS NULL` mà quên lọc trạng thái khi lookup thì sao?  
**Đáp án:** Có thể tìm thấy nhiều row cùng loginKey (một active, một soft-deleted), gây nhầm danh tính; phải đồng bộ index, query, restore policy.

**Câu 8.** Một bearer token có accountId đúng nhưng truy cập tài nguyên tenant khác; ID đúng có đủ để cho phép không?  
**Đáp án:** Không. Identity hợp lệ không thay thế tenant membership/ownership/authorization.

## 12. Checklist đưa vào production

- [ ] Xác định **một identity nội bộ bất biến** (accountId) và dùng nó cho FKs/audit.
- [ ] Định nghĩa login identifier và **phạm vi uniqueness**: global, tenant hoặc identity namespace khác.
- [ ] Chuẩn hóa và validate theo một policy có version/test; giữ **loginKey** thống nhất cho register, login, rename và migration.
- [ ] Có **UNIQUE constraint/index thật** trên khóa chính sách và composite FK nếu cần chống cross-tenant references.
- [ ] Có quy tắc cụ thể cho email/phone/external identity, nullable và verified state.
- [ ] Khi duplicate do concurrency, rollback/DO NOTHING đúng cách; không ghi đè account đang tồn tại.
- [ ] Phân loại lỗi unique **đúng constraint**, không che lỗi hạ tầng khác.
- [ ] Không dùng `findFirst` để né dữ liệu trùng; audit và dọn migration có kiểm soát.
- [ ] Đổi username giữ accountId, cập nhật cache/session và audit theo chính sách.
- [ ] Quy định soft-delete, phục hồi, tên cũ được tái sử dụng hay không, và chống mạo danh.
- [ ] Kiểm thử PostgreSQL thật về concurrent inserts, unique violation, collation và transaction.
- [ ] Giữ ranh giới giữa **account existence**, **authentication**, **authorization** và **data privacy**.

**Ghi nhớ:** **Tên đăng nhập là alias theo một namespace; account ID là danh tính nội bộ ổn định; unique constraint là cơ chế bảo đảm tính toàn vẹn cuối cùng khi nhiều request cùng ghi.** Khi Spring Security tải một người dùng để xác thực, nó phải nhận đúng một principal đã được xác định theo namespace và chính sách chuẩn hóa; không bao giờ lấy đại một bản ghi trong các tên trùng.

### Tài liệu chính thức để đối chiếu

- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `PRIMARY KEY`, `NOT NULL`, `CHECK`, `UNIQUE` và `FOREIGN KEY`; unique đa cột, NULL và partial unique index.
- [PostgreSQL — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html): cơ chế index cho unique constraint, uniqueness trên nhiều cột.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): xử lý conflict khi ghi và `RETURNING`.
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): `23505` / `unique_violation`.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetailsService.html): contract `loadUserByUsername`, trả `UserDetails` hoặc ném `UsernameNotFoundException`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): xác thực username/password sau khi tải dữ liệu bằng `UserDetailsService`.
