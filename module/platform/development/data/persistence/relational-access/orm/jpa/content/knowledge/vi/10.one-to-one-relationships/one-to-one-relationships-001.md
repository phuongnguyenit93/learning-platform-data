# Ánh xạ quan hệ một-một với khóa ngoại duy nhất trong JPA

## 1. Quan hệ một-một có khóa ngoại duy nhất là gì?

Trong mô hình dữ liệu quan hệ, **quan hệ một-một** (*one-to-one*) biểu diễn rằng một bản ghi ở phía A liên kết với **tối đa một** bản ghi ở phía B, và mỗi bản ghi B cũng liên kết với **tối đa một** bản ghi A. Một cách triển khai phổ biến là đặt **khóa ngoại** (*foreign key, FK*) ở một bảng rồi ràng buộc cột FK đó là **duy nhất** (*UNIQUE*).

Ví dụ trong hệ thống tài khoản:

- Bảng `accounts` lưu tài khoản đăng nhập.
- Bảng `account_settings` lưu thiết lập riêng của tài khoản.
- Mỗi `AccountSettings` thuộc **đúng một** `Account`.
- Mỗi `Account` có thể có **không hoặc một** `AccountSettings`.

Có thể hình dung như sau:

```text
accounts                                 account_settings
+---------------------+                  +----------------------------+
| id  (PRIMARY KEY)   |<-----------------| account_id (FOREIGN KEY)   |
| username            |       1       0..1| UNIQUE, NOT NULL          |
+---------------------+                  | id (PRIMARY KEY)           |
                                         | locale                     |
                                         | theme                      |
                                         +----------------------------+

account_settings.account_id:
  -> FOREIGN KEY tham chiếu accounts.id
  -> UNIQUE ngăn hai hàng settings thuộc cùng một account
  -> NOT NULL yêu cầu mỗi hàng settings phải có account
```

Điểm tạo nên **một-một ở phía database** là sự kết hợp của:

1. **FOREIGN KEY**: mỗi `account_settings.account_id` trỏ đến một tài khoản có thật.
2. **UNIQUE**: không có hai hàng thiết lập cùng trỏ đến một tài khoản.
3. **NOT NULL** nếu muốn mỗi thiết lập **bắt buộc** phải thuộc một tài khoản.

Bên cạnh đó, bảng `account_settings` vẫn có **khóa chính riêng** `id`. Đây là dấu hiệu khác biệt quan trọng so với kiểu một-một **dùng chung khóa chính** (*shared primary key*), trong đó cột FK đồng thời là PK của bảng phụ.

Trong **Jakarta Persistence (JPA)**, quan hệ này được ánh xạ chủ yếu bằng:

- `@OneToOne`: khai báo thuộc tính Java đại diện cho quan hệ một-một.
- `@JoinColumn`: khai báo cột FK trên **phía sở hữu quan hệ**.
- `unique = true` trên `@JoinColumn` hoặc ràng buộc UNIQUE trong DDL/migration: đảm bảo tính một-một ở cơ sở dữ liệu.
- `mappedBy`: khai báo phía **nghịch đảo** (*inverse side*) nếu muốn truy cập quan hệ theo hai chiều.

Bài này sử dụng gói API `jakarta.persistence`. Các dự án JPA cũ có thể dùng `javax.persistence`; phải giữ API/provider tương thích với nhau.

## 2. Quan hệ Java và ràng buộc SQL cần đi cùng nhau

### 2.1. Một thuộc tính Java không tự đảm bảo dữ liệu là một-một

Giả sử một entity có:

```java
@OneToOne
private Account account;
```

Về mặt object, thuộc tính `account` chỉ giữ **một tham chiếu `Account`**. Tuy nhiên, tính một-một trên **toàn bảng** còn yêu cầu: không được có hai `AccountSettings` khác nhau cùng giữ một `account_id`.

Nếu database không có unique constraint và provider/schema không thêm nó, dữ liệu có thể trở thành:

```text
account_settings
+----+------------+---------+
| id | account_id | theme   |
+----+------------+---------+
| 11 | 1          | dark    |
| 12 | 1          | light   |
+----+------------+---------+

Cả hai hàng đều trỏ đến accounts.id = 1.
=> Vi phạm ý nghĩa một-một.
```

Vì vậy, annotation `@OneToOne` thể hiện **mô hình ánh xạ**, còn UNIQUE constraint của database bảo vệ tính duy nhất ngay cả khi có nhiều ứng dụng, script SQL hoặc transaction cạnh tranh cùng ghi dữ liệu.

### 2.2. FK duy nhất không tự bắt buộc parent có child

Một bảng phụ có `account_id NOT NULL UNIQUE` bảo đảm:

- Mỗi **settings** phải trỏ đến một **account**.
- Mỗi **account** được trỏ đến bởi **tối đa một settings**.

Nó **không tự bảo đảm** mỗi tài khoản phải có bản ghi settings. Một account mới có thể tồn tại mà chưa có hàng trong `account_settings`.

Đây là khác biệt giữa:

| Ràng buộc | Ý nghĩa |
|---|---|
| `FOREIGN KEY` | ID tham chiếu phải tồn tại trong bảng được tham chiếu, trừ trường hợp FK cho phép NULL. |
| `UNIQUE` trên FK | Không có hai bản ghi phía giữ FK dùng cùng một giá trị FK không-null. |
| `NOT NULL` trên FK | Mỗi hàng phía giữ FK phải gắn với một parent. |
| Logic tạo account + settings trong cùng transaction | Giúp quy trình nghiệp vụ luôn tạo đủ hai đối tượng khi thao tác thành công. |
| Mỗi account bắt buộc phải có settings tại mọi thời điểm | Ràng buộc mạnh hơn; chỉ FK UNIQUE bên settings chưa đủ để database tự áp đặt. |

Nếu doanh nghiệp yêu cầu mỗi tài khoản luôn có settings, ứng dụng thường tạo cả hai bản ghi trong cùng transaction, có quy tắc khởi tạo và xử lý dữ liệu cũ thích hợp.

### 2.3. Một-một khác một-nhiều thế nào?

Trong quan hệ nhiều-một:

```java
@ManyToOne
@JoinColumn(name = "account_id")
private Account account;
```

Nhiều row phía có FK được phép dùng cùng `account_id`. Để thành quan hệ một-một ở database, FK cần được hạn chế UNIQUE. Annotation `@OneToOne` thể hiện rằng mỗi entity bên này chỉ tham chiếu một entity bên kia theo mô hình một-một; `UNIQUE` đảm bảo phía ngược lại không xuất hiện nhiều hàng cùng FK.

Không nên dùng `@ManyToOne` và chỉ dựa vào mã Java “không bao giờ tạo bản ghi trùng” nếu domain thực sự yêu cầu quan hệ một-một.

## 3. Thiết kế database: hai bảng, hai khóa chính và một FK UNIQUE

Một DDL minh họa:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE account_settings (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    locale VARCHAR(10) NOT NULL,
    theme VARCHAR(20) NOT NULL,

    CONSTRAINT fk_account_settings_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(id),

    CONSTRAINT uk_account_settings_account
        UNIQUE (account_id)
);
```

Cú pháp `IDENTITY` và kiểu SQL cụ thể thay đổi theo RDBMS; đoạn DDL minh họa ý tưởng dùng database có hỗ trợ cú pháp tương ứng.

Ví dụ dữ liệu hợp lệ:

```text
accounts
+----+-------------+
| id | username    |
+----+-------------+
| 10 | phuong      |
| 20 | minh        |
| 30 | lan         |
+----+-------------+

account_settings
+----+------------+--------+-------+
| id | account_id | locale | theme |
+----+------------+--------+-------+
| 51 | 10         | vi-VN  | dark  |
| 52 | 20         | en-US  | light |
+----+------------+--------+-------+

Account 10 -> settings 51.
Account 20 -> settings 52.
Account 30 -> chưa có settings; dữ liệu vẫn hợp lệ.
```

Nếu chèn thêm:

```sql
INSERT INTO account_settings (account_id, locale, theme)
VALUES (10, 'en-US', 'light');
```

database sẽ từ chối do `account_id = 10` đã được một hàng settings khác sử dụng. Cách hệ quản trị báo lỗi, thứ tự kiểm tra constraint và nội dung thông báo có thể khác nhau.

Nếu cố chèn `account_id = 999` trong khi không có `accounts.id = 999`, FOREIGN KEY sẽ từ chối. Nếu chèn `account_id = NULL`, NOT NULL sẽ từ chối.

**Vị trí đặt FK là một quyết định thiết kế.** Nếu FK nằm ở `account_settings`, thì bảng này đang giữ quan hệ. Có thể thiết kế ngược, để `accounts.settings_id` tham chiếu `account_settings.id` và UNIQUE trên `settings_id`. Điều quan trọng là chọn một nơi đặt FK rõ ràng và ánh xạ đúng phía sở hữu trong JPA.

## 4. Ánh xạ một chiều: `@OneToOne` và `@JoinColumn(unique = true)`

Bắt đầu với trường hợp đơn giản: `AccountSettings` biết `Account` của mình, nhưng `Account` không có thuộc tính đi ngược tới `AccountSettings`.

### 4.1. Entity `Account`

```java
package com.example.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, unique = true, length = 80)
    private String username;

    protected Account() {
        // Constructor không tham số cho JPA.
    }

    public Account(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Username không được trống");
        }
        this.username = username;
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }
}
```

`Account` là một entity thông thường, có khóa `Long id`. Ở mô hình một chiều này, nó **không biết trực tiếp** settings nào đang tham chiếu mình.

### 4.2. Entity `AccountSettings` giữ foreign key

```java
package com.example.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        referencedColumnName = "id",
        nullable = false,
        unique = true,
        foreignKey = @ForeignKey(name = "fk_account_settings_account")
    )
    private Account account;

    @Column(name = "locale", length = 10, nullable = false)
    private String locale;

    @Column(name = "theme", length = 20, nullable = false)
    private String theme;

    protected AccountSettings() {
        // Constructor không tham số cho JPA.
    }

    public AccountSettings(Account account, String locale, String theme) {
        this.account = Objects.requireNonNull(account, "account");
        this.locale = Objects.requireNonNull(locale, "locale");
        this.theme = Objects.requireNonNull(theme, "theme");
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }

    public String getLocale() {
        return locale;
    }

    public void changeLocale(String locale) {
        if (locale == null || locale.isBlank()) {
            throw new IllegalArgumentException("Locale không hợp lệ");
        }
        this.locale = locale;
    }
}
```

Trong mapping này, `AccountSettings.account` là **owning side** (*phía sở hữu*) vì nó chứa `@JoinColumn` quyết định giá trị FK `account_id`.

Phân tích:

| Cấu hình | Ý nghĩa |
|---|---|
| `@OneToOne` | Ánh xạ quan hệ một-một tới entity `Account`. |
| `fetch = FetchType.LAZY` | Đề nghị provider trì hoãn tải `Account` cho đến khi cần, nếu provider hỗ trợ. |
| `optional = false` | Mối liên kết phải có giá trị theo mô hình JPA. |
| `@JoinColumn(name = "account_id")` | Cột FK nằm trên bảng của `AccountSettings`. |
| `referencedColumnName = "id"` | FK tham chiếu cột `id` ở bảng `accounts`. Có thể bỏ nếu dùng PK mặc định theo quy tắc JPA. |
| `nullable = false` | Metadata sinh DDL cho cột FK `NOT NULL`. |
| `unique = true` | Yêu cầu unique constraint trên FK khi provider sinh schema. |
| `@ForeignKey(name = ...)` | Đặt tên ràng buộc FK trong DDL sinh ra, khi cơ chế sinh schema hỗ trợ. |

**`@OneToOne` không thay thế việc bảo đảm UNIQUE trên database production.** Nếu schema đã tồn tại và do migration quản lý, cần tạo ràng buộc SQL thực tế; annotation không tự di chuyển mọi schema hiện hữu.

### 4.3. Lưu dữ liệu với quan hệ một chiều

Giả sử ứng dụng Java SE đã có `EntityManagerFactory emf` cho persistence unit kiểu `RESOURCE_LOCAL`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Account account = new Account("phuong");
    em.persist(account);

    AccountSettings settings = new AccountSettings(
        account,
        "vi-VN",
        "dark"
    );
    em.persist(settings);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Để lưu một `AccountSettings` có FK không-null, ứng dụng cần gắn một `Account` hợp lệ. Ví dụ trên persist parent trước, child sau trong một transaction. Provider sẽ cấp ID cho parent và dùng ID đó làm giá trị `account_id` khi ghi child, theo thứ tự SQL phù hợp.

Vì mapping này **không khai báo cascade**, gọi `em.persist(settings)` tự nó không có nghĩa parent mới cũng được persist. Nếu cần tự động persist parent từ child, phải đánh giá vòng đời nghiệp vụ rồi mới thêm `cascade`.

Với **JTA/container-managed transaction**, phần `EntityTransaction` không được dùng trên entity manager JTA. Service sẽ nhận transaction do container hoặc framework điều phối.

## 5. Ánh xạ hai chiều: `mappedBy` và phía sở hữu

Trường hợp thường gặp hơn là:

- `Account.getSettings()` trả về settings tương ứng.
- `AccountSettings.getAccount()` trả về account sở hữu.

Đây là **một quan hệ một-một duy nhất có thể điều hướng hai chiều**, chứ không phải hai quan hệ độc lập.

### 5.1. Bên giữ FK là owning side

Nếu database có `account_settings.account_id`, mapping bên settings là:

```java
@OneToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private Account account;
```

Bên account khai báo **inverse side**:

```java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountSettings settings;
```

`mappedBy = "account"` có nghĩa: thuộc tính `settings` của `Account` được ánh xạ bởi thuộc tính Java **`account`** trên `AccountSettings`. Giá trị `"account"` là **tên field/property Java**, không phải tên SQL `"account_id"`.

Một sơ đồ rõ về quyền sở hữu:

```text
Java:
Account.settings --------------------- AccountSettings.account
     inverse                                owning
  mappedBy="account"                       @JoinColumn("account_id")

SQL:
accounts.id <------------------------- account_settings.account_id
                                        FOREIGN KEY + UNIQUE
```

Ở phía inverse, không đặt `@JoinColumn(name = "account_id")` như thể cột đó thuộc bảng `accounts`. Nếu cả hai phía đều khai báo quan hệ sở hữu riêng, provider có thể diễn giải thành **hai FK/quan hệ khác nhau** và sinh schema sai thiết kế.

### 5.2. Entity hai chiều với helper đồng bộ

Trong ví dụ đầy đủ sau, `Account` có thể tạo kèm settings và cascade `PERSIST` đến settings. Phía settings vẫn giữ cột FK.

`Account.java`:

```java
package com.example.account;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "username", nullable = false, length = 80, unique = true)
    private String username;

    @OneToOne(
        mappedBy = "account",
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST
    )
    private AccountSettings settings;

    protected Account() {}

    public Account(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("Username không hợp lệ");
        }
        this.username = username;
    }

    public Long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public AccountSettings getSettings() {
        return settings;
    }

    public void attachSettings(AccountSettings newSettings) {
        Objects.requireNonNull(newSettings, "newSettings");

        if (this.settings != null) {
            throw new IllegalStateException(
                "Tài khoản đã có settings"
            );
        }

        // Cập nhật cả phía inverse và owning side.
        this.settings = newSettings;
        newSettings.attachAccount(this);
    }
}
```

`AccountSettings.java`:

```java
package com.example.account;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "account_settings")
public class AccountSettings {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;

    @Column(name = "locale", length = 10, nullable = false)
    private String locale;

    @Column(name = "theme", length = 20, nullable = false)
    private String theme;

    protected AccountSettings() {}

    public AccountSettings(String locale, String theme) {
        if (locale == null || locale.isBlank()) {
            throw new IllegalArgumentException("Locale không hợp lệ");
        }
        if (theme == null || theme.isBlank()) {
            throw new IllegalArgumentException("Theme không hợp lệ");
        }
        this.locale = locale;
        this.theme = theme;
    }

    // Package-private: chỉ service/aggregate quản lý liên kết.
    void attachAccount(Account account) {
        Objects.requireNonNull(account, "account");

        if (this.account != null && this.account != account) {
            throw new IllegalStateException(
                "Settings đã thuộc một tài khoản khác"
            );
        }

        this.account = account;
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }

    public String getLocale() {
        return locale;
    }

    public String getTheme() {
        return theme;
    }

    public void changeTheme(String theme) {
        if (theme == null || theme.isBlank()) {
            throw new IllegalArgumentException("Theme không hợp lệ");
        }
        this.theme = theme;
    }
}
```

Trong hai class này:

- `AccountSettings.account` vẫn là **owning side**, có `@JoinColumn(unique = true)`.
- `Account.settings` chỉ là **inverse side**, dùng `mappedBy = "account"`.
- `Account.attachSettings()` bảo đảm cả hai tham chiếu Java nhất quán.
- `cascade = CascadeType.PERSIST` giúp `em.persist(account)` persist settings mới được gắn; đây là lựa chọn phù hợp khi tạo aggregate. Nó **không đồng nghĩa** tự động merge hay remove settings trong các thao tác khác.
- Không cần dùng `@GeneratedValue` cho `account_id`: nó chỉ là FK đến ID của Account; khóa chính riêng `AccountSettings.id` mới được sinh bằng IDENTITY.

Helper trên được thiết kế chỉ để **gắn settings lần đầu**. Nếu nghiệp vụ cho phép chuyển settings giữa tài khoản, xóa hoặc thay thế, cần thêm phương thức được kiểm soát để xử lý cả phía owning, inverse và ràng buộc UNIQUE/NOT NULL một cách nhất quán.

### 5.3. Persist parent và cascade child

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Account account = new Account("minh");
    AccountSettings settings =
            new AccountSettings("vi-VN", "dark");

    account.attachSettings(settings);

    // CascadeType.PERSIST trên Account.settings.
    em.persist(account);

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Nếu transaction commit thành công, database có account và settings tương ứng. Một ví dụ SQL do provider có thể tạo theo trình tự:

```sql
INSERT INTO accounts (username) VALUES ('minh');

-- Giả sử database cấp accounts.id = 15.

INSERT INTO account_settings (account_id, locale, theme)
VALUES (15, 'vi-VN', 'dark');
```

Provider sử dụng bind parameters và có thể tạo SQL khác về cú pháp, thứ tự cột, thời điểm flush. Đoạn SQL chỉ giúp hình dung **FK được lấy từ Account.id**, không phải yêu cầu ứng dụng tự viết SQL.

## 6. Phân biệt `optional`, `nullable` và `unique`

Ba thuộc tính giải quyết ba vấn đề khác nhau:

```java
@OneToOne(optional = false)
@JoinColumn(
    name = "account_id",
    nullable = false,
    unique = true
)
private Account account;
```

| Thuộc tính | Thuộc API | Quy định |
|---|---|---|
| `optional = false` | `@OneToOne` | Thuộc tính quan hệ bắt buộc có đối tượng tham chiếu theo mô hình persistence. |
| `nullable = false` | `@JoinColumn` | Cột FK không nhận SQL NULL trong DDL được sinh. |
| `unique = true` | `@JoinColumn` | Cột FK có ràng buộc UNIQUE trong DDL được sinh. |

Một số lưu ý:

- `optional = false` không tự diễn đạt tính **duy nhất**; vẫn cần UNIQUE thực tế ở schema.
- `unique = true` không đồng nghĩa FK phải có giá trị; nếu muốn phía giữ FK bắt buộc có parent, kết hợp `nullable = false` và mô hình `optional = false`.
- `nullable = false` trên `account_settings.account_id` không ép bảng `accounts` phải có settings.
- Các metadata này giúp provider tạo DDL và hiểu mapping; **schema đã tồn tại** cần migration tương ứng.
- `@NotNull` của Jakarta Bean Validation có thể bổ sung kiểm tra thuộc tính, nhưng phải có Bean Validation provider/integration; annotation đó không thay thế khóa ngoại/unique constraint của database.

### 6.1. Nếu FK cho phép NULL

Một quan hệ một-một có FK nullable vẫn hợp lệ trong một số domain:

```sql
CREATE TABLE employees (
    id BIGINT PRIMARY KEY,
    parking_spot_id BIGINT UNIQUE NULL,
    FOREIGN KEY (parking_spot_id) REFERENCES parking_spots(id)
);
```

Khi đó nhân viên có thể chưa được cấp chỗ đỗ xe, nhưng một chỗ đỗ xe không thể đồng thời được gán cho hai nhân viên theo unique constraint.

**NULL và UNIQUE có khác biệt theo RDBMS.** Nhiều hệ quản trị cho phép nhiều hàng có `NULL` trong một cột UNIQUE, vì NULL không được xem như một giá trị bằng nhau thông thường; một số hệ có quy tắc hoặc tùy chọn index/constraint khác. Khi dùng unique trên FK nullable, cần kiểm tra hành vi của database mục tiêu.

Đối với bài toán settings bắt buộc có account ở phía giữ FK, ví dụ dùng `nullable = false` để tránh sự khác biệt này.

### 6.2. Unique constraint ở cấp bảng

Có thể khai báo uniqueness rõ bằng `@Table`:

```java
@Entity
@Table(
    name = "account_settings",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_account_settings_account",
        columnNames = "account_id"
    )
)
public class AccountSettings {
    // ...

    @OneToOne(optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;
}
```

`@JoinColumn(unique = true)` là cách viết ngắn để biểu đạt uniqueness trên cột FK. `@Table(uniqueConstraints = ...)` hữu ích khi cần **tên constraint** hoặc nhiều cột phối hợp. Với một FK đơn, thường chỉ cần một trong hai cách cho mục đích DDL; không nên khai báo vô tình thành nhiều unique constraint trùng chức năng.

Nếu schema production được quản lý bằng Flyway, Liquibase hoặc SQL migration, constraint UNIQUE cần thực sự tồn tại trong database, dù annotation dùng dạng nào.

## 7. Tìm kiếm và truy vấn theo quan hệ một-một

### 7.1. Truy vấn theo phía giữ FK

Với mô hình hai chiều:

```java
AccountSettings settings = em.createQuery(
    """
    SELECT s
    FROM AccountSettings s
    WHERE s.account.id = :accountId
    """,
    AccountSettings.class
)
.setParameter("accountId", 15L)
.getResultStream()
.findFirst()
.orElse(null);
```

`s.account.id` là đường dẫn **thuộc tính entity** trong JPQL. Provider chuyển đổi thành SQL phù hợp, thường có thể lọc bằng FK `account_id`.

Vì mỗi account chỉ có tối đa một settings, `getSingleResult()` có thể được sử dụng khi chắc chắn tồn tại; nhưng nó ném exception nếu không có kết quả. Ví dụ dùng `getResultStream().findFirst()` để trả `null` nếu account chưa có settings.

### 7.2. Truy vấn từ inverse side

`Account` có thể truy cập:

```java
Account account = em.find(Account.class, 15L);

if (account != null) {
    AccountSettings settings = account.getSettings();
    if (settings != null) {
        System.out.println(settings.getTheme());
    }
}
```

Khi nào `getSettings()` kích hoạt truy vấn phụ phụ thuộc trạng thái persistence context, fetch type và provider. Đừng giả định chỉ một lệnh SQL vì `Account` đã được load.

### 7.3. `LEFT JOIN FETCH` khi settings là optional

Nếu muốn lấy Account **cùng settings nếu có** trong cùng câu truy vấn:

```java
Account account = em.createQuery(
    """
    SELECT a
    FROM Account a
    LEFT JOIN FETCH a.settings
    WHERE a.id = :id
    """,
    Account.class
)
.setParameter("id", 15L)
.getResultStream()
.findFirst()
.orElse(null);
```

Dùng `LEFT JOIN FETCH` vì Account có thể **không có settings**. Nếu dùng `INNER JOIN FETCH`, những tài khoản chưa có settings có thể bị loại khỏi kết quả.

Với nhiều account:

```java
List<Account> accounts = em.createQuery(
    """
    SELECT a
    FROM Account a
    LEFT JOIN FETCH a.settings
    ORDER BY a.id
    """,
    Account.class
).getResultList();
```

Một-một không tạo phép nhân số bản ghi như một quan hệ một-nhiều, miễn dữ liệu đáp ứng UNIQUE. Tuy nhiên, fetch strategy còn liên quan tới số SQL, bộ nhớ và kế hoạch truy vấn. Cần chọn fetch theo nhu cầu của màn hình/API thay vì mặc định luôn tải toàn bộ object graph.

### 7.4. Criteria API

Có thể lọc AccountSettings theo Account ID bằng Criteria:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<AccountSettings> query =
        cb.createQuery(AccountSettings.class);

Root<AccountSettings> settings =
        query.from(AccountSettings.class);

query.select(settings).where(
    cb.equal(settings.get("account").get("id"), 15L)
);

List<AccountSettings> result =
        em.createQuery(query).getResultList();
```

Trong dự án lớn, JPA static metamodel hoặc Criteria có kiểu rõ ràng giúp giảm lỗi do gõ sai tên thuộc tính chuỗi.

## 8. Fetch strategy: `EAGER`, `LAZY` và vấn đề hiệu năng

Mặc định theo JPA, `@OneToOne` sử dụng **`FetchType.EAGER`** nếu không chỉ rõ. Điều này thể hiện yêu cầu provider sẵn sàng cung cấp quan hệ khi entity được truy cập theo cách phù hợp.

```java
@OneToOne
private Account account; // Mặc định EAGER.
```

Nếu muốn ưu tiên tải trì hoãn:

```java
@OneToOne(fetch = FetchType.LAZY)
private Account account;
```

**`LAZY` là gợi ý** đối với provider; khả năng thực hiện lazy loading có thể khác nhau, nhất là với phía inverse của one-to-one. Một số provider cần bytecode enhancement hoặc cơ chế đặc biệt để biết một đối tượng ở phía inverse có quan hệ hay không mà không phải query bổ sung.

### 8.1. Vì sao phía inverse đôi khi tải thêm SQL?

Account giữ thuộc tính:

```java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountSettings settings;
```

Trong bảng `accounts` **không có FK `settings_id`**. Để biết một account có settings hay không, provider có thể phải tra bảng `account_settings` theo `account_id`. Vì thế ngay cả khi khai báo LAZY, provider có thể chạy truy vấn bổ sung trong một số tình huống.

Đây là tính chất của mô hình **FK nằm bên kia**, không phải lỗi khai báo `mappedBy`. Nếu đối tượng liên quan luôn cần được hiển thị, dùng truy vấn `LEFT JOIN FETCH` hoặc entity graph; nếu không cần, cần đo hành vi provider thực tế.

### 8.2. N+1 trên quan hệ một-một

Giả sử lấy 100 tài khoản rồi gọi `getSettings()` cho từng tài khoản:

```java
List<Account> accounts = em.createQuery(
    "SELECT a FROM Account a",
    Account.class
).getResultList();

for (Account account : accounts) {
    AccountSettings settings = account.getSettings();
    // Có thể phát sinh truy vấn phụ để tìm settings.
}
```

Nếu provider phải truy vấn settings riêng cho mỗi account, kết quả có thể là **1 query lấy accounts + nhiều query lấy settings** (*N+1*). Cách khắc phục phụ thuộc nhu cầu truy vấn và provider: `JOIN FETCH`, entity graph, batch fetching hoặc projection DTO.

Không nên coi `fetch = LAZY` là bảo đảm tự động loại N+1; đây chỉ là một phần của chiến lược truy cập dữ liệu.

### 8.3. EntityManager đóng sớm

Nếu entity manager/persistence context đã đóng và quan hệ chưa tải, việc truy cập quan hệ lazy có thể thất bại theo hành vi provider. Đối với API trả JSON/DTO, nên lấy đủ dữ liệu cần thiết trong transaction hoặc persistence context thích hợp, rồi chuyển thành DTO. Không nên dựa vào việc serialization tự kích hoạt hàng loạt truy vấn sau khi service đã kết thúc.

## 9. Cascade: truyền thao tác giữa hai entity

`CascadeType` quy định các thao tác JPA có được lan truyền từ entity này sang entity kia hay không:

| Cascade | Khi nào có tác dụng |
|---|---|
| `PERSIST` | `persist(parent)` truyền sang entity liên quan được cấu hình. |
| `MERGE` | `merge(parent)` thực hiện merge cho entity liên quan theo quan hệ được cascade. |
| `REMOVE` | `remove(parent)` truyền thao tác xóa sang entity liên quan. |
| `REFRESH` | Refresh state liên quan. |
| `DETACH` | Detach entity liên quan khỏi persistence context. |
| `ALL` | Bao gồm tất cả các loại cascade trên. |

Trong ví dụ account và settings, nếu **settings là thành phần phụ thuộc vòng đời account**, có thể cân nhắc:

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountSettings settings;
```

Lúc này:

- Persist account có thể persist settings.
- Merge account có thể merge settings.
- Remove account có thể remove settings.
- Nếu một settings managed bị loại khỏi quan hệ và `orphanRemoval = true` được áp dụng theo quy tắc JPA, provider sẽ xử lý xóa entity phụ thuộc.

Nhưng **đây là lựa chọn nghiệp vụ**, không phải yêu cầu bắt buộc của quan hệ một-một. Nếu entity liên quan có vòng đời độc lập, ví dụ `Person` và `Passport`, cascade `REMOVE` có thể gây mất dữ liệu không mong muốn.

### 9.1. Cascade không đồng nghĩa DB `ON DELETE CASCADE`

`CascadeType.REMOVE` là cơ chế **JPA truyền lệnh remove trong persistence context**, còn `ON DELETE CASCADE` là quy tắc **foreign key ở database**. Chúng hoạt động ở những tầng khác nhau.

```text
JPA CascadeType.REMOVE
  -> provider xử lý remove của entity liên quan
  -> thực thi SQL tương ứng trong transaction

SQL ON DELETE CASCADE
  -> database tự xử lý hàng con khi hàng cha bị xóa
     theo constraint đã cấu hình
```

Chỉ khai báo `cascade = REMOVE` không mặc nhiên tạo `ON DELETE CASCADE` trong mọi schema. Ngược lại, database tự cascade xóa bằng SQL ngoài JPA không tự cập nhật trạng thái mọi object managed đang nằm trong persistence context.

### 9.2. `orphanRemoval` khi xóa quan hệ

Trong một mô hình account sở hữu settings, có thể bật:

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private AccountSettings settings;
```

Khi loại một settings khỏi quan hệ được quản lý, provider có thể xóa settings theo cơ chế orphan removal khi đồng bộ. Cần viết helper cập nhật **cả hai phía** quan hệ:

```java
public void removeSettings() {
    if (settings != null) {
        settings.detachFromAccount();
        settings = null;
    }
}
```

Mã trên là **phác thảo**; `detachFromAccount()` phải được triển khai phù hợp trong `AccountSettings`, và việc gỡ liên kết trên một entity còn tồn tại với FK `NOT NULL` sẽ không hợp lệ nếu không thực sự xóa entity phụ thuộc. Khi sử dụng `orphanRemoval`, cần để provider xử lý xóa trong transaction thích hợp; không dùng thao tác gỡ liên kết như thể muốn giữ settings không có account.

`orphanRemoval` phù hợp khi đối tượng con không còn ý nghĩa tồn tại độc lập sau khi bị tách khỏi parent. Nếu muốn **chuyển** settings sang account khác, orphan removal có thể không phải lựa chọn đúng.

### 9.3. Xóa account khi không có cascade remove

Trong mô hình hai chiều ở phần 5 chỉ có `CascadeType.PERSIST`. Nếu xóa account mà settings vẫn tham chiếu nó, database có thể báo vi phạm FK. Một service có thể xử lý bằng transaction:

```java
Account account = em.find(Account.class, accountId);

if (account != null) {
    AccountSettings settings = account.getSettings();

    if (settings != null) {
        em.remove(settings);
    }

    em.remove(account);
}
```

Các thao tác phải chạy trong transaction; provider quản lý thứ tự SQL theo dependency. Nếu hệ thống có quan hệ khác tới account, chúng cũng cần được xử lý theo quy tắc riêng.

## 10. Giữ hai phía quan hệ nhất quán trong bộ nhớ

Trong **bidirirectional one-to-one**, cần cập nhật object graph ở cả hai phía:

```java
Account account = new Account("lan");
AccountSettings settings =
        new AccountSettings("vi-VN", "light");

account.attachSettings(settings);
```

Sau đó:

```java
account.getSettings() == settings; // true
settings.getAccount() == account;  // true
```

Nếu chỉ gán inverse side nhưng quên owning side:

```java
// Ví dụ một helper sai:
this.settings = settings;
// settings.account vẫn null.
```

thì provider nhìn thấy owning side `AccountSettings.account` không có giá trị. Vì FK ở bảng settings là NOT NULL, việc ghi có thể thất bại, ngay cả khi phía `Account.settings` trong bộ nhớ có tham chiếu.

Ngược lại, nếu chỉ gán `settings.account = account` nhưng không cập nhật `account.settings`, FK có thể được ghi đúng theo owning side, nhưng object graph hiện tại không phản ánh đúng quan hệ hai chiều cho tới khi reload/refresh.

**Quy tắc thực hành:** tạo helper ở tầng domain để quản lý liên kết và tránh setter công khai độc lập ở cả hai phía. Đồng thời giữ UNIQUE constraint ở database để bảo vệ trường hợp hai transaction hoặc client cùng tạo settings cho một account.

## 11. Những tình huống cần kiểm soát đồng thời

### 11.1. Hai transaction cùng tạo settings

Giả sử account ID 10 chưa có settings:

```text
Transaction T1                     Transaction T2
---------------------------        ---------------------------
SELECT settings account_id=10      SELECT settings account_id=10
  -> chưa có                          -> chưa có

INSERT account_settings(...10)     INSERT account_settings(...10)

COMMIT                              COMMIT / lỗi UNIQUE
```

Cả hai transaction đều có thể thấy “chưa có” vì thời điểm và mức isolation. Không thể bảo đảm một-một chỉ bằng kiểm tra ứng dụng:

```java
if (findSettings(accountId) == null) {
    em.persist(newSettings);
}
```

Ràng buộc `UNIQUE(account_id)` mới là lớp bảo vệ cuối cùng. Một transaction sẽ có thể thất bại khi INSERT/COMMIT vì trùng unique. Service cần xử lý exception phù hợp và quyết định có retry, trả lỗi nghiệp vụ hoặc tải lại settings hiện có hay không.

Nếu yêu cầu cập nhật đồng thời phức tạp, có thể cân nhắc optimistic locking với `@Version` hoặc khóa pessimistic theo nhu cầu, nhưng **không thay thế UNIQUE constraint** bằng cơ chế khóa ứng dụng.

### 11.2. Chuyển một settings từ account này sang account khác

Nếu có settings S đang thuộc account A, chuyển sang B có thể vi phạm quy tắc domain hoặc làm object graph không nhất quán. Unique constraint cũng có thể chặn nếu B đã có settings.

Với entity có vòng đời phụ thuộc parent, thường **không cho phép chuyển owner tùy ý**. Nếu nghiệp vụ cần, phải thiết kế thao tác rõ ràng, cập nhật cả hai phía và xử lý trùng FK/unique trong transaction.

### 11.3. Hoán đổi settings giữa hai account

Khi A có settings S1, B có settings S2, cập nhật S1 sang B và S2 sang A trong cùng transaction có thể va unique constraint ở các bước SQL trung gian, dù trạng thái cuối cùng trông hợp lệ. Transaction không bảo đảm một SQL engine sẽ trì hoãn kiểm tra UNIQUE đến commit, trừ khi database/constraint hỗ trợ điều đó.

Hệ thống nên tránh thao tác hoán đổi owner nếu không thực sự cần, hoặc thiết kế quy trình chuyển dữ liệu phù hợp ràng buộc và khả năng database.

## 12. One-to-one với khóa ngoại duy nhất và shared primary key

Hai mô hình cùng diễn đạt quan hệ một-một nhưng **schema và định danh khác nhau**.

### 12.1. Khóa ngoại duy nhất, khóa chính riêng

```text
accounts                   account_settings
id (PK)     <------------- account_id (FK, UNIQUE)
                           id (PK riêng)
```

Mapping:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;

@OneToOne(optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private Account account;
```

Đặc điểm:

- `AccountSettings.id` độc lập với `Account.id`.
- `account_id` là FK có UNIQUE; không phải PK.
- Settings có thể giữ ID kỹ thuật ổn định khi yêu cầu nghiệp vụ thay đổi quan hệ, miễn việc chuyển liên kết được thiết kế và cho phép.
- Sơ đồ database có hai khóa chính và một cột FK bổ sung.

### 12.2. Shared primary key bằng `@MapsId`

```text
accounts                   account_settings
id (PK)     <------------- account_id (PK, FK)
                           không có PK riêng khác
```

Mapping rút gọn:

```java
@Id
@Column(name = "account_id")
private Long id;

@MapsId
@OneToOne(optional = false)
@JoinColumn(name = "account_id", nullable = false)
private Account account;
```

Ở mô hình này, `AccountSettings.id` bằng `Account.id`. Không cần cột `account_settings.id` riêng. `@MapsId` biểu diễn **định danh dẫn xuất**: khóa của settings đến từ account.

| Tiêu chí | FK duy nhất + PK riêng | Shared primary key |
|---|---|---|
| PK của bảng settings | `id` riêng | `account_id` đồng thời là PK |
| FK | `account_id UNIQUE` | `account_id` vừa PK vừa FK |
| Kỹ thuật JPA điển hình | `@OneToOne + @JoinColumn(unique=true)` | `@OneToOne + @MapsId` |
| Định danh settings phụ thuộc ID của account? | Không, mặc dù quan hệ bắt buộc. | Có. |
| Thay đổi account liên quan | Có thể về mặt schema nếu domain cho phép và UNIQUE còn hợp lệ. | Là thay đổi định danh của settings; thường không nên. |
| Số cột khóa kỹ thuật | Hai khóa riêng trên hai bảng, thêm FK. | Ít cột dư hơn ở bảng dependent. |

Khi đề bài là **“Ánh xạ quan hệ một-một với khóa ngoại duy nhất”**, trọng tâm là mô hình **PK riêng + FK UNIQUE**. `@MapsId` là giải pháp khác cho trường hợp domain yêu cầu settings lấy chính định danh account làm định danh của mình.

## 13. One-to-one một chiều với FK ở phía còn lại

Không phải lúc nào entity phụ trợ mới là phía giữ FK. Ví dụ mỗi nhân viên có tối đa một chỗ đỗ xe và mỗi chỗ chỉ gán một nhân viên:

```text
parking_spots              employees
+----------+               +---------------------------+
| id (PK)  |<--------------| parking_spot_id (FK,UNIQUE)|
| code     |               | id (PK)                   |
+----------+               | name                      |
                           +---------------------------+
```

Nếu mỗi employee được phép không có chỗ đỗ, `parking_spot_id` có thể NULL.

Entity một chiều:

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", nullable = false)
    private String name;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "parking_spot_id",
        nullable = true,
        unique = true
    )
    private ParkingSpot parkingSpot;

    protected Employee() {}

    public void assignParkingSpot(ParkingSpot parkingSpot) {
        this.parkingSpot = parkingSpot;
    }
}
```

Khóa chính `ParkingSpot.id` vẫn độc lập với `Employee.id`. UNIQUE trên `employees.parking_spot_id` ngăn một chỗ đỗ xe được gán cho nhiều nhân viên.

Qua ví dụ này có thể rút ra: **phía sở hữu trong JPA là phía giữ cột FK theo mapping**, không phải nhất thiết entity “cha” hoặc entity có vai trò quan trọng hơn trong nghiệp vụ.

## 14. Lựa chọn giữa `@JoinColumn` và `@JoinTable`

Quan hệ một-một cũng có thể được ánh xạ qua **bảng liên kết** (*join table*), nhưng mô hình FK UNIQUE ở một trong hai bảng thường đơn giản hơn nếu không cần lưu liên kết riêng.

### 14.1. FK trực tiếp trong bảng settings

```text
accounts
  id

account_settings
  id
  account_id  -- FK UNIQUE
```

Ưu điểm:

- Ít bảng và ít join hơn trong nhiều truy vấn.
- Dễ đọc ràng buộc: một settings thuộc đúng một account.
- Thuận tiện nếu settings có vòng đời phụ thuộc account.

### 14.2. Join table riêng

```text
accounts
  id

account_settings
  id

account_settings_links
  account_id  -- FK, UNIQUE
  settings_id -- FK, UNIQUE
```

Muốn đảm bảo một-một qua bảng liên kết, thường phải ràng buộc **duy nhất cả hai phía** (hoặc dùng khóa chính/unique tương đương), nếu không một account có thể liên kết nhiều settings hoặc một settings liên kết nhiều account.

Cơ chế join table có thể phù hợp với một số schema legacy hoặc khi quan hệ được quản lý riêng, nhưng nếu không có yêu cầu đó, FK UNIQUE trực tiếp thường dễ triển khai và ít thành phần hơn.

## 15. Đặt unique constraint trong migration và xử lý dữ liệu hiện có

Một thay đổi phổ biến là chuyển quan hệ từ **nhiều-một** sang **một-một**. Giả sử bảng `account_settings` đã có cột `account_id` nhưng chưa UNIQUE.

Không nên chỉ sửa Java:

```java
// Trước:
@ManyToOne
@JoinColumn(name = "account_id")
private Account account;

// Sau:
@OneToOne
@JoinColumn(name = "account_id", unique = true)
private Account account;
```

Nếu schema production không được provider cập nhật tự động, database vẫn có thể cho phép duplicate FK. Nếu thêm UNIQUE vào bảng đã có duplicate, migration có thể thất bại.

### 15.1. Kiểm tra dữ liệu trùng trước khi thêm UNIQUE

Ví dụ SQL:

```sql
SELECT account_id, COUNT(*) AS row_count
FROM account_settings
WHERE account_id IS NOT NULL
GROUP BY account_id
HAVING COUNT(*) > 1;
```

Nếu có kết quả, phải quyết định theo nghiệp vụ:

- Giữ hàng settings nào làm bản ghi chính?
- Cần hợp nhất dữ liệu từ các hàng trùng không?
- Những tham chiếu tới hàng bị xóa có cần cập nhật không?
- Có cần lưu lịch sử hoặc audit trước khi xóa/hợp nhất không?

Sau khi giải quyết dữ liệu trùng, thêm constraint bằng cú pháp phù hợp hệ quản trị:

```sql
ALTER TABLE account_settings
ADD CONSTRAINT uk_account_settings_account
UNIQUE (account_id);
```

Nếu cần FK bắt buộc, kiểm tra các hàng null và xử lý trước khi đặt `NOT NULL`. Trong môi trường có nhiều instance ứng dụng, nên bảo đảm các phiên bản đang chạy tuân thủ rule mới để không ghi thêm duplicate trong lúc migration.

### 15.2. Tên constraint giúp vận hành

Tên như `uk_account_settings_account` và `fk_account_settings_account` giúp nhận diện lỗi trong log:

```text
Constraint violation:
  uk_account_settings_account
```

Không nên phụ thuộc vào thông báo exception cụ thể để viết toàn bộ business logic, vì provider và database có thể bọc lỗi khác nhau; nhưng đặt tên constraint nhất quán có ích khi vận hành, chẩn đoán và viết migration.

### 15.3. Đừng dùng `drop-and-create` cho dữ liệu thật

Trong bài thực hành, `jakarta.persistence.schema-generation.database.action=drop-and-create` có thể giúp provider tạo bảng và constraint từ annotation. Với database production, nó có thể **xóa dữ liệu**.

Ứng dụng thật nên có chiến lược migration rõ ràng (Flyway, Liquibase hoặc SQL script được quản lý) để sửa bảng, kiểm tra dữ liệu cũ và khôi phục khi cần.

## 16. Lỗi thường gặp với quan hệ một-một FK UNIQUE

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai settings cùng trỏ một account | Không có UNIQUE thực trên `account_id`, hoặc schema chưa được migration. | Tạo UNIQUE constraint ở DB; xử lý duplicate dữ liệu cũ. |
| Mỗi entity tự sinh một FK khác nhau | Hai phía cùng dùng `@JoinColumn` mà thiếu `mappedBy`. | Chỉ định một owning side giữ FK và một inverse side dùng `mappedBy`. |
| `mappedBy = "account_id"` báo lỗi | `mappedBy` cần **tên thuộc tính Java**, không phải SQL column. | Dùng `mappedBy = "account"` nếu bên kia có field `account`. |
| FK null dù `Account.settings` đã gán | Chỉ cập nhật phía inverse, quên `AccountSettings.account`. | Dùng helper cập nhật hai phía; owning side phải đúng. |
| Lỗi NOT NULL trên cột FK | Child chưa gắn parent hợp lệ hoặc quan hệ không được gán trước flush. | Gắn parent và persist theo transaction thích hợp. |
| Dùng `optional = false` nhưng vẫn có hai child cho một parent | `optional` không bảo đảm uniqueness. | Giữ constraint UNIQUE; kiểm tra transaction đồng thời. |
| `@OneToOne(fetch = LAZY)` vẫn thấy query phụ | LAZY chỉ là gợi ý và inverse one-to-one có thể cần query để xác định có child hay không. | Đo hành vi provider, dùng fetch join/entity graph khi cần. |
| N+1 khi duyệt danh sách account | Truy cập settings của từng account làm phát sinh query riêng. | Chọn fetch strategy phù hợp với truy vấn cụ thể. |
| Xóa account bị vi phạm FK | Settings còn tham chiếu account, chưa có cascade/remove phù hợp. | Xóa dependent trước hoặc thiết kế cascade/orphan removal đúng vòng đời. |
| Xóa account lại xóa entity quan trọng khác | Cấu hình `CascadeType.REMOVE` hoặc `ALL` trên quan hệ có lifecycle độc lập. | Chỉ dùng remove cascade khi child thực sự phụ thuộc parent. |
| Thay đổi account của settings gây trùng unique | Account mới đã có settings hoặc thao tác swap gây va UNIQUE. | Kiểm soát invariant và thứ tự thay đổi trong transaction. |
| Chỉ thêm `@JoinColumn(unique=true)` nhưng DB production chưa có UNIQUE | Annotation không thay thế migration. | Đưa constraint vào DDL/migration và xác nhận schema thực tế. |
| Có settings mới nhưng không được persist khi persist account | Không có cascade PERSIST từ account sang settings. | Persist settings riêng hoặc thêm cascade nếu phù hợp aggregate. |
| Lỗi lazy access khi serialize ngoài persistence context | Quan hệ chưa tải trước khi EntityManager đóng. | Fetch dữ liệu cần thiết trong service và chuyển sang DTO. |
| Nhầm FK duy nhất với shared PK | Child có `id` riêng nhưng lại cố dùng `@MapsId`. | Chọn rõ FK UNIQUE + PK riêng hoặc shared PK, ánh xạ nhất quán. |
| Dữ liệu tùy chọn dùng UNIQUE nullable có hành vi khác môi trường | Quy tắc UNIQUE đối với NULL khác giữa các RDBMS. | Kiểm tra schema/dialect, cân nhắc ràng buộc hoặc index đặc thù. |

### 16.1. Tại sao không đặt cả `@OneToOne` và `@ManyToOne` lên cùng field?

Đó là hai quan hệ cardinality khác nhau và không nên khai báo đồng thời để “tăng tính chắc chắn”. Hãy xác định cardinality của mô hình, chọn một annotation phù hợp, rồi đưa constraint tương ứng vào database.

### 16.2. Tại sao `unique=true` chưa đủ để bảo đảm mọi account có settings?

Unique chỉ kiểm soát **không trùng** trong các giá trị được lưu. Nó không buộc phải tồn tại một hàng trong bảng settings cho mỗi account. Nếu business rule bắt buộc, hãy thiết kế quy trình tạo/xóa và transaction phù hợp, có thể cùng validation/application service.

### 16.3. Đặt FK ở bảng nào thì tốt hơn?

Không có quy tắc tuyệt đối. Xem xét:

- Đối tượng nào có vòng đời phụ thuộc đối tượng kia?
- Phía nào bắt buộc có tham chiếu và có thể dùng `NOT NULL`?
- Chiều truy vấn thường gặp từ service/API?
- Cấu trúc schema đã tồn tại hay cần tương thích legacy?
- Mong muốn xóa cascade, chuyển liên kết hoặc tách bảng?

Với settings phụ thuộc account, FK ở `account_settings` thường tự nhiên. Nếu một entity chính chỉ có thể tham chiếu một đối tượng phụ nhưng đối tượng phụ có vòng đời riêng và liên kết tùy chọn, FK có thể đặt ở bảng chính. Cách chọn phải được phản ánh nhất quán ở `@JoinColumn` và `mappedBy`.

## 17. Bài thực hành từ đầu đến cuối

### 17.1. Thiết lập persistence unit Java SE

Dùng entity `Account` và `AccountSettings` của phần 5. Một file `src/main/resources/META-INF/persistence.xml` cho H2 trong bộ nhớ có thể là:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="accountPU"
                      transaction-type="RESOURCE_LOCAL">

        <class>com.example.account.Account</class>
        <class>com.example.account.AccountSettings</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:accountdb;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Để chạy cần **Jakarta Persistence API**, **một JPA provider** (chẳng hạn Hibernate ORM hoặc EclipseLink tương thích) và **H2 JDBC driver**. Cấu hình `drop-and-create` chỉ dành cho thực hành, không dùng với dữ liệu cần giữ.

### 17.2. Lưu account và settings trong một transaction

```java
package com.example.account;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class OneToOneUniqueFkDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
                Persistence.createEntityManagerFactory("accountPU");

        try {
            Long accountId = createAccountWithSettings(emf);
            showAccount(emf, accountId);
        } finally {
            emf.close();
        }
    }

    private static Long createAccountWithSettings(
            EntityManagerFactory emf
    ) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Account account = new Account("duy");
                AccountSettings settings =
                        new AccountSettings("vi-VN", "dark");

                // Helper duy trì cả hai phía.
                account.attachSettings(settings);

                // Cascade PERSIST sang settings.
                em.persist(account);

                // Với IDENTITY, provider có thể phải INSERT để có id.
                em.flush();
                Long id = account.getId();

                tx.commit();
                return id;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }

    private static void showAccount(
            EntityManagerFactory emf,
            Long accountId
    ) {
        EntityManager em = emf.createEntityManager();

        try {
            Account account = em.createQuery(
                """
                SELECT a
                FROM Account a
                LEFT JOIN FETCH a.settings
                WHERE a.id = :id
                """,
                Account.class
            )
            .setParameter("id", accountId)
            .getSingleResult();

            System.out.println(account.getUsername());

            AccountSettings settings = account.getSettings();
            if (settings != null) {
                System.out.println(settings.getLocale());
                System.out.println(settings.getTheme());
                System.out.println(settings.getAccount().getId());
            }
        } finally {
            em.close();
        }
    }
}
```

Bài thực hành này sử dụng Java có hỗ trợ **text block** (`"""`), ví dụ Java 17. Khi dùng Java phiên bản cũ hơn, thay JPQL text block bằng chuỗi thông thường.

Kết quả mong đợi về mặt dữ liệu:

```text
accounts:
  (id=<ID>, username="duy")

account_settings:
  (id=<ID_riêng>, account_id=<ID>,
   locale="vi-VN", theme="dark")
```

Ở đây, `AccountSettings.id` là một khóa chính **khác**, do database cấp riêng; `AccountSettings.account.id` và `account_settings.account_id` cùng trỏ đến `Account.id`. Đó chính là mô hình **một-một qua FK UNIQUE**.

### 17.3. Kiểm tra các tính chất của mô hình

Có thể tự thực hành theo các tình huống:

1. Tạo hai account khác nhau, mỗi account một settings: cả hai đều được lưu.
2. Tạo một account không gọi `attachSettings`: account vẫn được lưu nếu business rule cho phép.
3. Cố gắng lưu **hai settings khác nhau cùng tham chiếu một account**: cơ sở dữ liệu phải từ chối bằng UNIQUE constraint khi SQL thực sự được thực thi.
4. Cố gắng lưu settings có `account == null`: mô hình `optional = false` và `NOT NULL` không cho phép dữ liệu đó.
5. Load account bằng `LEFT JOIN FETCH` khi chưa có settings: kết quả account vẫn có thể được trả về, `getSettings()` là `null`.
6. Thử xóa account vẫn còn settings với chỉ cascade `PERSIST`: database có thể chặn xóa vì FK; thiết kế thao tác xóa dependent hoặc cascade phù hợp.

Các tình huống này phân biệt **ràng buộc schema**, **metadata JPA**, **lifecycle trong persistence context** và **quy tắc nghiệp vụ** — bốn tầng liên quan nhưng không thay thế nhau.

## 18. Câu hỏi tự kiểm tra

**1. Cột nào nên có UNIQUE trong ví dụ Account–AccountSettings?**

`account_settings.account_id`, bởi đây là khóa ngoại từ settings tới account. UNIQUE ngăn hai settings cùng tham chiếu một account.

**2. Vì sao chỉ có `@OneToOne` trên field Java chưa phải bảo đảm cuối cùng?**

Vì dữ liệu có thể được ghi từ nhiều transaction, ứng dụng khác hoặc SQL trực tiếp. UNIQUE constraint trong database là lớp bảo vệ nhất quán cho toàn bảng.

**3. `@JoinColumn(unique = true)` và `@OneToOne(optional = false)` có cùng ý nghĩa không?**

Không. `unique = true` yêu cầu duy nhất giá trị FK; `optional = false` nói rằng quan hệ phải có giá trị theo mô hình entity.

**4. Nếu có `account_id NOT NULL UNIQUE` thì mỗi account bắt buộc có settings không?**

Không. Mỗi settings bắt buộc thuộc một account, và mỗi account có tối đa một settings. Account vẫn có thể chưa có settings.

**5. Trong mapping hai chiều, `mappedBy = "account"` trỏ tới đâu?**

Nó trỏ tới **tên thuộc tính Java `account` trong `AccountSettings`**, là phía sở hữu có `@JoinColumn`. Không trỏ tới SQL column `account_id`.

**6. Vì sao cần helper như `Account.attachSettings()`?**

Helper gán cả `Account.settings` và `AccountSettings.account`, giúp hai phía trong object graph nhất quán. Phía owning mới quyết định FK được ghi.

**7. `FetchType.LAZY` có bảo đảm provider không query settings khi load Account?**

Không. Với `@OneToOne`, LAZY là gợi ý; phía inverse có thể cần query để xác định child có tồn tại hay không. Kết quả phụ thuộc provider và cấu hình enhancement.

**8. `CascadeType.PERSIST` có tự động xóa settings khi xóa account không?**

Không. PERSIST chỉ áp dụng thao tác persist. Xóa cần thiết kế riêng bằng remove explicit, `CascadeType.REMOVE` hoặc cơ chế liên quan phù hợp.

**9. FK UNIQUE khác shared primary key ở điểm nào?**

Với FK UNIQUE, settings có PK `id` riêng và cột `account_id` là FK UNIQUE. Với shared primary key, `account_id` vừa là FK vừa chính là PK của settings, thường ánh xạ bằng `@MapsId`.

**10. Nếu hai transaction cùng thấy account chưa có settings rồi cùng INSERT thì sao?**

Cả hai có thể cùng bắt đầu thao tác, nhưng UNIQUE constraint ngăn hai hàng có cùng `account_id` cùng tồn tại khi commit/ghi hoàn tất. Ứng dụng phải xử lý lỗi uniqueness theo quy tắc nghiệp vụ.

## 19. Ghi nhớ trọng tâm

Để ánh xạ một quan hệ **một-một với khóa ngoại duy nhất** trong JPA, cần hiểu đồng thời ba lớp:

1. **Schema quan hệ:** một bảng giữ FK đến bảng kia và có **UNIQUE** trên FK; kết hợp `NOT NULL` khi liên kết là bắt buộc ở phía giữ FK.
2. **Mapping JPA:** owning side khai báo `@OneToOne + @JoinColumn(name = "...", unique = true)`; nếu hai chiều, inverse side khai báo `@OneToOne(mappedBy = "tenThuocTinhOwner")`.
3. **Vòng đời nghiệp vụ:** đồng bộ hai tham chiếu Java, chọn cascade phù hợp, đặt transaction đúng phạm vi, kiểm soát truy vấn/fetch và bảo vệ các tình huống ghi đồng thời bằng constraint database.

Mẫu cơ bản:

```java
// Owning side, bảng này giữ FK UNIQUE.
@OneToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private Account account;

// Inverse side, trên entity Account:
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountSettings settings;
```

**`@OneToOne` mô tả cardinality của object model; UNIQUE trên FK bảo đảm cardinality đó trong dữ liệu quan hệ.** Khi kết hợp hai cơ chế đúng, ứng dụng có thể đọc và ghi hai entity qua JPA một cách nhất quán, đồng thời để database duy trì ràng buộc giữa mọi transaction.

### Tài liệu tham khảo

- [Jakarta Persistence — đặc tả chính thức](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `@OneToOne`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/onetoone)
- [Jakarta Persistence API — `@JoinColumn`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/joincolumn)
- [Jakarta Persistence API — `@Table`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/table)
