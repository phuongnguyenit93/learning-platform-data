# Điều kiện IsNull, IsNotNull, True và False

Trong **Spring Data Relational JDBC**, derived query cho phép biểu diễn điều kiện truy vấn ngay trong tên phương thức repository. Bốn điều kiện thường dùng là:

- **IsNull:** tìm các hàng mà property có giá trị SQL `NULL`.
- **IsNotNull:** tìm các hàng mà property có giá trị khác `NULL`.
- **True:** tìm các hàng mà property boolean là `TRUE`.
- **False:** tìm các hàng mà property boolean là `FALSE`.

Các từ khóa này hữu ích khi truy vấn dữ liệu chưa được điền, dữ liệu soft delete, trạng thái bật/tắt và các cờ nghiệp vụ. Tuy nhiên, cần hiểu đúng ngữ nghĩa `NULL` của SQL: `NULL` không phải `FALSE`, và điều kiện so sánh với `NULL` không hoạt động giống so sánh hai giá trị thông thường.

Bài học giải thích cú pháp method name, cách Spring Data JDBC chuyển điều kiện thành truy vấn SQL, cách kết hợp nhiều predicate, và những lỗi dễ gặp khi dùng kiểu `Boolean` nullable.

## 1. Derived query trong Spring Data JDBC

Spring Data JDBC có thể tạo truy vấn từ tên method trong repository. Thay vì tự viết SQL cho các điều kiện đơn giản, bạn khai báo tên method theo quy tắc query derivation.

Ví dụ:

```java
public interface UserAccountRepository
        extends CrudRepository<UserAccount, Long> {

    List<UserAccount> findByDeletedAtIsNull();

    List<UserAccount> findByDeletedAtIsNotNull();

    List<UserAccount> findByEnabledTrue();

    List<UserAccount> findByEnabledFalse();
}
```

Spring Data phân tích tên method để nhận biết:

- **Subject:** phần mô tả loại kết quả/thao tác, ví dụ `find`, `count`, `exists`.
- **Predicate:** phần sau `By`, mô tả property và điều kiện.
- **Property path:** tên property Java cần truy vấn.
- **Operator/keyword:** điều kiện như `IsNull`, `IsNotNull`, `True`, `False`, `And`, `Or`.

Ví dụ `findByDeletedAtIsNull()` có nghĩa: tìm các `UserAccount` có property `deletedAt` đang null. `findByEnabledTrue()` có nghĩa: tìm các account có `enabled` bằng true.

**Tên property trong method là tên property Java**, không phải tên cột SQL. Nếu property `deletedAt` được ánh xạ sang cột `deleted_at`, method vẫn dùng `DeletedAt`.

## 2. IsNull: tìm property có giá trị NULL

`IsNull` biểu diễn điều kiện SQL `IS NULL`.

Ví dụ một account chưa bị soft delete có `deletedAt = null`:

```java
List<UserAccount> findByDeletedAtIsNull();
```

Một method khác:

```java
List<UserAccount> findByEmailIsNull();
```

Ngữ nghĩa tương ứng:

```sql
SELECT *
FROM user_accounts
WHERE deleted_at IS NULL;
```

Hoặc:

```sql
SELECT *
FROM user_accounts
WHERE email IS NULL;
```

Không cần truyền tham số cho `IsNull`, vì điều kiện không so sánh property với một giá trị do caller cung cấp. Nó kiểm tra trực tiếp trạng thái null của cột.

### 2.1. Alias Null

Spring Data query derivation hỗ trợ cả `IsNull` và `Null` cho điều kiện null. Ví dụ:

```java
List<UserAccount> findByDeletedAtNull();
```

Tuy vậy, `IsNull` thường dễ đọc hơn vì diễn đạt rõ đây là predicate kiểm tra null.

### 2.2. Khi nào dùng IsNull?

Một số tình huống thường gặp:

| Property | Ý nghĩa của NULL | Method ví dụ |
|---|---|---|
| `deletedAt` | Bản ghi chưa bị soft delete | `findByDeletedAtIsNull()` |
| `verifiedAt` | Chưa xác minh | `findByVerifiedAtIsNull()` |
| `publishedAt` | Chưa được xuất bản | `findByPublishedAtIsNull()` |
| `assignedTo` | Chưa được giao người xử lý | `findByAssignedToIsNull()` |
| `closedAt` | Ticket chưa đóng | `findByClosedAtIsNull()` |

Chỉ dùng `IsNull` khi null có ý nghĩa domain rõ ràng. Không nên dùng null như một giá trị thay thế tùy tiện cho nhiều trạng thái khác nhau.

## 3. IsNotNull: tìm property đã có giá trị

`IsNotNull` biểu diễn SQL `IS NOT NULL`.

Ví dụ:

```java
List<UserAccount> findByDeletedAtIsNotNull();

List<UserAccount> findByEmailIsNotNull();
```

SQL tương ứng về ngữ nghĩa:

```sql
SELECT *
FROM user_accounts
WHERE deleted_at IS NOT NULL;
```

```sql
SELECT *
FROM user_accounts
WHERE email IS NOT NULL;
```

Method này trả về các hàng mà cột có một giá trị, kể cả khi giá trị đó là chuỗi rỗng hoặc số 0. `IS NOT NULL` không kiểm tra nội dung có hợp lệ hay không; nó chỉ kiểm tra cột có phải SQL NULL hay không.

### 3.1. Alias NotNull

Có thể viết `NotNull` thay cho `IsNotNull`:

```java
List<UserAccount> findByEmailNotNull();
```

Cả hai biểu đạt cùng điều kiện. Nên thống nhất một kiểu đặt tên trong codebase để repository dễ đọc.

### 3.2. IsNotNull không có nghĩa là chuỗi không rỗng

Ví dụ:

| `email` trong database | `email IS NOT NULL` |
|---|---|
| `NULL` | Không thỏa |
| Chuỗi rỗng (`''`) | Thỏa |
| Chỉ có khoảng trắng (`'   '`) | Thỏa |
| `linh@example.com` | Thỏa |

Nếu nghiệp vụ cần chuỗi khác rỗng, cần điều kiện khác như `Not` với chuỗi rỗng, validation hoặc query tường minh. `IsNotNull` không tự trim hoặc kiểm tra độ dài.

## 4. True và False: điều kiện boolean

Với property boolean, Spring Data hỗ trợ các từ khóa `True` và `False`.

Ví dụ:

```java
List<UserAccount> findByEnabledTrue();

List<UserAccount> findByEnabledFalse();
```

Hai method có ngữ nghĩa:

- `findByEnabledTrue()`: chỉ lấy hàng có `enabled = TRUE`.
- `findByEnabledFalse()`: chỉ lấy hàng có `enabled = FALSE`.

Có thể dùng alias `IsTrue` và `IsFalse`:

```java
List<UserAccount> findByEnabledIsTrue();

List<UserAccount> findByEnabledIsFalse();
```

Hai kiểu tên method biểu đạt cùng predicate. `True`/`False` thường ngắn gọn và dễ đọc.

### 4.1. SQL tương ứng

Trên database có kiểu BOOLEAN, ngữ nghĩa truy vấn tương tự:

```sql
SELECT *
FROM user_accounts
WHERE enabled = TRUE;
```

và:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE;
```

Cú pháp literal boolean cụ thể có thể khác giữa hệ quản trị. Spring Data JDBC dùng dialect và mapping của database để xây dựng truy vấn; không nên tự thay bằng `= 1` hoặc `= 'Y'` nếu chưa xét database và kiểu cột.

### 4.2. True/False không phải IsNull/IsNotNull

Nếu property là kiểu `Boolean` (wrapper) và cột cho phép NULL, có ba trạng thái dữ liệu:

1. `TRUE`
2. `FALSE`
3. `NULL`

`findByEnabledTrue()` chỉ tìm trạng thái thứ nhất. `findByEnabledFalse()` chỉ tìm trạng thái thứ hai. Cả hai đều không trả về hàng có `enabled = NULL`.

Nếu cần truy vấn trạng thái thứ ba, dùng `findByEnabledIsNull()`.

## 5. SQL NULL và logic ba giá trị

Đây là điểm quan trọng nhất khi kết hợp điều kiện null và boolean.

Trong SQL, biểu thức điều kiện có thể cho kết quả:

- `TRUE`
- `FALSE`
- `UNKNOWN`

Khi một phép so sánh liên quan tới `NULL`, kết quả thường là `UNKNOWN`, không phải `TRUE` hay `FALSE`.

Ví dụ:

```sql
enabled = TRUE
enabled = FALSE
enabled <> TRUE
enabled = NULL
```

Nếu `enabled` là NULL, các phép so sánh trên không cho kết quả TRUE. Vì `WHERE` chỉ chọn hàng mà predicate là TRUE, hàng có NULL sẽ không xuất hiện trong kết quả.

Để kiểm tra null, SQL yêu cầu cú pháp:

```sql
enabled IS NULL
enabled IS NOT NULL
```

Bảng chân trị rút gọn:

| Giá trị `enabled` | `enabled = TRUE` | `enabled = FALSE` | `enabled IS NULL` | `enabled IS NOT NULL` |
|---|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE | TRUE |
| FALSE | FALSE | TRUE | FALSE | TRUE |
| NULL | UNKNOWN | UNKNOWN | TRUE | FALSE |

Đây là lý do `findByEnabledFalse()` không có nghĩa là “không true, kể cả null”. Nó có nghĩa chính xác là “bằng false”.

### 5.1. Tìm false hoặc chưa xác định

Nếu nghiệp vụ coi cả `FALSE` và `NULL` là trạng thái chưa bật, hãy diễn đạt cả hai điều kiện:

```java
List<UserAccount> findByEnabledFalseOrEnabledIsNull();
```

Ngữ nghĩa SQL:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE
   OR enabled IS NULL;
```

Tương tự, nếu cần account đã bật hoặc chưa có trạng thái:

```java
List<UserAccount> findByEnabledTrueOrEnabledIsNull();
```

Hãy xác định ý nghĩa nghiệp vụ của null trước khi kết hợp. Null có thể có nghĩa “chưa thiết lập”, “không biết”, “không áp dụng” hoặc “dữ liệu cũ chưa được migration”. Không nên tự động gộp null vào false nếu domain cần phân biệt chúng.

## 6. Ví dụ domain và repository hoàn chỉnh

Giả sử bảng `user_accounts` lưu tài khoản người dùng, gồm email, trạng thái kích hoạt, trạng thái xác minh và thời điểm soft delete.

### 6.1. Schema

Ví dụ DDL cho PostgreSQL:

```sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255),
    enabled BOOLEAN,
    verified BOOLEAN,
    deleted_at TIMESTAMP
);
```

Trong ví dụ này:

- `email` cho phép NULL để minh họa `IsNull`.
- `enabled` và `verified` là BOOLEAN nullable.
- `deleted_at` cho phép NULL; NULL có nghĩa tài khoản chưa bị soft delete.

Schema production có thể cần thêm `NOT NULL`, unique constraint, index và các ràng buộc nghiệp vụ khác. Nếu `enabled` luôn bắt buộc phải có giá trị, nên khai báo `NOT NULL` và cân nhắc backfill dữ liệu cũ trước khi áp dụng.

### 6.2. Domain class

```java
import java.time.LocalDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("user_accounts")
public class UserAccount {

    @Id
    private Long id;

    private String email;

    private Boolean enabled;

    private Boolean verified;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    protected UserAccount() {
    }

    public UserAccount(
            String email,
            Boolean enabled,
            Boolean verified
    ) {
        this.email = email;
        this.enabled = enabled;
        this.verified = verified;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public Boolean getVerified() {
        return verified;
    }

    public LocalDateTime getDeletedAt() {
        return deletedAt;
    }
}
```

Các annotation và kiểu dữ liệu:

- `@Table` là annotation Spring Data Relational để ánh xạ bảng.
- `@Id` là annotation Spring Data để chỉ định identifier.
- `@Column("deleted_at")` ánh xạ property `deletedAt` sang cột `deleted_at`.
- `Boolean` cho phép biểu diễn cả true, false và null.

### 6.3. Repository

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface UserAccountRepository
        extends CrudRepository<UserAccount, Long> {

    // Null predicates
    List<UserAccount> findByEmailIsNull();

    List<UserAccount> findByEmailIsNotNull();

    List<UserAccount> findByDeletedAtIsNull();

    List<UserAccount> findByDeletedAtIsNotNull();

    // Boolean predicates
    List<UserAccount> findByEnabledTrue();

    List<UserAccount> findByEnabledFalse();

    List<UserAccount> findByEnabledIsNull();

    List<UserAccount> findByVerifiedTrue();

    List<UserAccount> findByVerifiedFalse();

    // Kết hợp boolean và null
    List<UserAccount> findByEnabledFalseOrEnabledIsNull();

    List<UserAccount> findByVerifiedTrueAndEnabledFalse();

    // Các subject khác ngoài find
    long countByDeletedAtIsNull();

    boolean existsByEmailIsNotNull();
}
```

Tên method được phân tích khi Spring tạo repository query. Nếu tên property hoặc keyword không hợp lệ, ứng dụng có thể báo lỗi lúc khởi động hoặc lúc tạo query tùy cấu hình.

## 7. Kết hợp IsNull/IsNotNull với True/False và các keyword khác

Derived query cho phép nối nhiều điều kiện bằng `And` và `Or`.

### 7.1. Dùng And

Ví dụ tìm tài khoản đã bật, đã xác minh và chưa bị soft delete:

```java
List<UserAccount>
findByEnabledTrueAndVerifiedTrueAndDeletedAtIsNull();
```

SQL tương đương về ngữ nghĩa:

```sql
SELECT *
FROM user_accounts
WHERE enabled = TRUE
  AND verified = TRUE
  AND deleted_at IS NULL;
```

Một hàng chỉ được trả về khi tất cả điều kiện đều TRUE. Hàng có `enabled`, `verified` hoặc `deleted_at` là NULL sẽ không thỏa predicate tương ứng.

### 7.2. Dùng Or

Tìm account chưa bật hoặc chưa có thời điểm xác minh:

```java
List<UserAccount>
findByEnabledFalseOrVerifiedAtIsNull();
```

Trong ví dụ này, `verifiedAt` cần là một property của domain class và được ánh xạ tới cột tương ứng.

SQL tương đương:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE
   OR verified_at IS NULL;
```

`Or` có nghĩa chỉ cần một nhánh predicate đúng. Nếu một nhánh trả UNKNOWN do NULL, nhánh còn lại vẫn có thể làm toàn biểu thức thành TRUE.

### 7.3. Kết hợp And và Or

Tên method có cả `And` và `Or` cần được đọc cẩn thận. Query derivation phân tách predicate thành các nhánh OR, trong mỗi nhánh có thể có nhiều điều kiện AND. Không nên viết một method rất dài rồi dựa vào cách đọc tự nhiên của con người để đoán thứ tự nhóm.

Ví dụ, nếu muốn biểu diễn:

```sql
WHERE (enabled = TRUE AND deleted_at IS NULL)
   OR (enabled = FALSE AND verified IS NULL)
```

hãy đặt tên method và kiểm tra query tạo ra, hoặc dùng `@Query` SQL tường minh nếu biểu thức cần nhóm phức tạp. Derived method name không phải nơi thuận tiện để biểu đạt các biểu thức ngoặc lồng nhau nhiều tầng.

## 8. Kết hợp với count, exists và các kiểu kết quả

Các predicate `IsNull`, `IsNotNull`, `True`, `False` không chỉ dùng với `find`.

### 8.1. Count

```java
long countByDeletedAtIsNull();

long countByEnabledTrue();

long countByEnabledFalse();
```

Các method này trả về số hàng thỏa điều kiện, không tải toàn bộ danh sách object.

### 8.2. Exists

```java
boolean existsByEmailIsNull();

boolean existsByEnabledTrue();
```

Dùng `exists` khi chỉ cần biết có bản ghi phù hợp hay không. Nó diễn đạt ý định rõ hơn việc gọi `find...` rồi kiểm tra list có rỗng hay không.

### 8.3. Optional và List

Nếu điều kiện không bảo đảm duy nhất, dùng `List<T>`:

```java
List<UserAccount> findByEnabledTrue();
```

Chỉ dùng `Optional<T>` khi domain/schema bảo đảm tối đa một kết quả:

```java
Optional<UserAccount> findById(Long id);
```

Một method như `findByEmailIsNull()` thường có thể trả về nhiều hàng, vì vậy không nên khai báo `Optional<UserAccount>` nếu nhiều tài khoản được phép thiếu email. Nếu repository query trả nhiều hàng nhưng method yêu cầu một kết quả duy nhất, Spring Data có thể báo lỗi kết quả không đúng số lượng.

## 9. Phân biệt Boolean primitive và Boolean wrapper

Java có hai kiểu thường dùng:

| Kiểu | Giá trị biểu diễn | Có thể null? |
|---|---|---|
| `boolean` | `true`, `false` | Không |
| `Boolean` | `Boolean.TRUE`, `Boolean.FALSE`, `null` | Có |

Nếu database column cho phép NULL, property Java nên dùng `Boolean` nếu ứng dụng cần giữ được trạng thái chưa xác định.

Ví dụ:

```java
private Boolean enabled;
```

Khi đọc dữ liệu, property có thể là `null`. Repository có thể truy vấn trạng thái đó bằng:

```java
List<UserAccount> findByEnabledIsNull();
```

Nếu dùng primitive:

```java
private boolean enabled;
```

thì Java object không thể biểu diễn null. Hãy thiết kế schema `NOT NULL` và default phù hợp nếu nghiệp vụ chỉ có hai trạng thái true/false. Nếu cột hiện tại nullable nhưng domain dùng primitive, cần xử lý dữ liệu NULL trước hoặc định nghĩa mapping/conversion phù hợp; không nên để trạng thái thiếu dữ liệu bị biến thành false một cách vô tình.

### 9.1. Null không tự động chuyển thành false

Không nên nghĩ rằng:

```java
Boolean enabled = null;
```

tương đương:

```java
Boolean enabled = false;
```

Đó là hai trạng thái khác nhau. Nếu business rule nói null phải được xem như false, hãy thể hiện rõ trong query hoặc migration:

```java
List<UserAccount> findByEnabledFalseOrEnabledIsNull();
```

Hoặc cập nhật dữ liệu để chuyển null thành false rồi đặt cột `NOT NULL`, nếu đó là quy tắc chính thức.

## 10. Derived query so với @Query SQL

Với điều kiện đơn giản, derived method thường dễ đọc:

```java
List<UserAccount> findByDeletedAtIsNull();

List<UserAccount> findByEnabledTrue();
```

Khi cần SQL đặc thù hoặc biểu thức phức tạp, Spring Data JDBC cho phép khai báo `@Query` với SQL phù hợp database.

Ví dụ:

```java
import org.springframework.data.jdbc.repository.query.Query;

@Query("""
    SELECT *
    FROM user_accounts
    WHERE deleted_at IS NULL
      AND enabled = TRUE
    """)
List<UserAccount> findActiveEnabledAccounts();
```

Đây là SQL, không phải JPQL. `@Query` trong Spring Data JDBC phải được viết theo dialect/schema mà database sử dụng. Cú pháp Java text block yêu cầu Java phiên bản hỗ trợ text block; nếu dự án dùng Java cũ hơn, có thể viết chuỗi thông thường.

Dùng derived query khi:

- Predicate đơn giản, có keyword được hỗ trợ.
- Tên method vẫn đủ ngắn và dễ hiểu.
- Không cần database-specific expression.

Dùng `@Query` khi:

- Có biểu thức phức tạp hoặc cần ngoặc rõ ràng.
- Cần join, projection hoặc SQL đặc thù.
- Tên derived method trở nên dài và khó đọc.
- Muốn kiểm soát trực tiếp câu SQL được thực thi.

Không dùng `@Query` chỉ để thay một `IsNull` đơn giản nếu derived method đã diễn đạt rõ ý định.

## 11. Property name, Column name và reserved words

Một lỗi thường gặp là dùng tên cột thay cho property name trong method.

Ví dụ domain:

```java
@Column("deleted_at")
private LocalDateTime deletedAt;
```

Method đúng:

```java
List<UserAccount> findByDeletedAtIsNull();
```

Không viết:

```java
List<UserAccount> findByDeleted_atIsNull();
```

Derived query phân tích property của domain model, nên dùng camelCase Java property. `@Column` chỉ điều khiển mapping property sang tên cột SQL.

Nếu property có tên dễ gây nhầm hoặc trùng từ khóa, hãy đặt tên Java rõ nghĩa và dùng `@Column` để ánh xạ tới tên schema cần thiết.

## 12. Kiểm thử các điều kiện null và boolean

Một test cần dữ liệu đủ cả ba trạng thái của Boolean nullable.

Ví dụ fixture:

| email | enabled | deleted_at | Ý nghĩa |
|---|---|---|---|
| a@example.com | TRUE | NULL | Đang bật, chưa soft delete |
| b@example.com | FALSE | NULL | Đang tắt, chưa soft delete |
| NULL | NULL | NULL | Chưa có email và chưa xác định enabled |
| d@example.com | TRUE | timestamp | Đã soft delete |

Test với Spring Boot JDBC slice:

```java
@DataJdbcTest
class UserAccountRepositoryTest {

    @Autowired
    UserAccountRepository accounts;

    @Test
    void distinguishesNullTrueAndFalse() {
        assertThat(accounts.findByEnabledTrue())
                .extracting(UserAccount::getEmail)
                .contains("a@example.com", "d@example.com");

        assertThat(accounts.findByEnabledFalse())
                .extracting(UserAccount::getEmail)
                .containsExactly("b@example.com");

        assertThat(accounts.findByEnabledIsNull())
                .hasSize(1);
    }

    @Test
    void findsSoftDeletedAndNotDeletedAccounts() {
        assertThat(accounts.findByDeletedAtIsNull())
                .hasSize(3);

        assertThat(accounts.findByDeletedAtIsNotNull())
                .hasSize(1);
    }
}
```

Test này giả định fixture đã được insert trước khi assertions chạy và schema cho phép các giá trị NULL tương ứng. Các import test như `@DataJdbcTest`, `@Autowired`, `@Test` và AssertJ cần có trong test dependencies của dự án.

### 12.1. Kiểm tra SQL khi cần

Nếu kết quả không như mong đợi, hãy quan sát câu SQL được thực thi và dữ liệu thật trong bảng. Có thể bật log JDBC trong môi trường test/dev:

```properties
logging.level.org.springframework.jdbc.core=DEBUG
```

Log phụ thuộc logger và phiên bản Spring. Không bật log nhạy cảm trên production nếu câu lệnh/parameter có thể chứa dữ liệu cá nhân.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `findByEnabledFalse()` không trả về hàng có enabled NULL | False và NULL là hai trạng thái khác nhau | Dùng `findByEnabledFalseOrEnabledIsNull()` nếu nghiệp vụ cần cả hai |
| `findByEmailIsNotNull()` vẫn trả về chuỗi rỗng | `IS NOT NULL` chỉ kiểm tra null | Thêm điều kiện kiểm tra chuỗi rỗng/blank hoặc validation |
| Method không được phân tích | Sai tên property hoặc keyword | Đối chiếu Java property và keyword Spring Data hỗ trợ |
| Dùng tên cột trong method nhưng query lỗi | Derived query cần property name | Dùng camelCase property, không dùng SQL column name |
| Dùng `findByEnabledTrue(Boolean value)` nhưng method không hợp lý | Keyword True là điều kiện cố định, không cần tham số | Dùng `findByEnabledTrue()` |
| `Optional` gây lỗi nhiều kết quả | Điều kiện null có thể khớp nhiều hàng | Dùng `List` hoặc đảm bảo uniqueness |
| Boolean nullable bị mất trạng thái null | Domain dùng primitive `boolean` hoặc dữ liệu bị chuẩn hóa | Dùng `Boolean` nếu cần ba trạng thái; xử lý migration |
| Query `Not` không trả về NULL | SQL `<>` cho kết quả UNKNOWN với NULL | Thêm `OrPropertyIsNull` nếu muốn bao gồm null |
| SQL literal boolean khác giữa database | Dialect/kiểu cột khác nhau | Dùng derived predicate hoặc viết SQL theo DB cụ thể |
| Test không có hàng NULL | Fixture hoặc schema không cho phép NULL | Kiểm tra DDL và dữ liệu test |

## 14. Bảng tham chiếu nhanh

| Mục tiêu | Derived method | Ngữ nghĩa SQL |
|---|---|---|
| Property là NULL | `findByPropertyIsNull()` | `property IS NULL` |
| Property khác NULL | `findByPropertyIsNotNull()` | `property IS NOT NULL` |
| Property boolean là true | `findByEnabledTrue()` | `enabled = TRUE` về ngữ nghĩa |
| Property boolean là false | `findByEnabledFalse()` | `enabled = FALSE` về ngữ nghĩa |
| Property boolean là null | `findByEnabledIsNull()` | `enabled IS NULL` |
| False hoặc null | `findByEnabledFalseOrEnabledIsNull()` | `enabled = FALSE OR enabled IS NULL` |
| True và chưa soft delete | `findByEnabledTrueAndDeletedAtIsNull()` | `enabled = TRUE AND deleted_at IS NULL` |
| Đếm bản ghi chưa soft delete | `countByDeletedAtIsNull()` | `COUNT` với `deleted_at IS NULL` |
| Có bản ghi có email | `existsByEmailIsNotNull()` | Kiểm tra tồn tại với `email IS NOT NULL` |

## 15. Nguyên tắc ghi nhớ

- **IsNull** và **IsNotNull** kiểm tra trạng thái NULL của property; chúng không so sánh với tham số.
- **True** và **False** là predicate boolean cố định; không cần truyền `true`/`false` vào method.
- Với property `Boolean` nullable, có ba trạng thái `TRUE`, `FALSE`, `NULL`. `findByEnabledFalse()` không bao gồm NULL.
- SQL dùng `IS NULL`/`IS NOT NULL`; không dùng `= NULL`/`<> NULL`.
- `And` và `Or` có thể kết hợp nhiều predicate, nhưng biểu thức phức tạp nên dùng SQL tường minh để tránh nhầm nhóm điều kiện.
- Derived method dùng **tên property Java**; `@Column` mới ánh xạ property sang tên cột database.
- Chọn `List`, `Optional`, `count` hoặc `exists` theo số lượng kết quả và mục tiêu truy vấn.

Khi dùng các điều kiện null và boolean, hãy bắt đầu từ ý nghĩa của từng trạng thái dữ liệu trong domain. Nếu NULL biểu thị “chưa biết” hoặc “chưa thiết lập”, giữ nó tách biệt với FALSE. Khi quy tắc nghiệp vụ cần gộp hai trạng thái, viết điều kiện `Or...IsNull` rõ ràng. Cách đặt tên method đúng sẽ giúp Spring Data JDBC tạo truy vấn dễ hiểu và giúp người đọc repository nắm được ý nghĩa dữ liệu ngay từ code.
