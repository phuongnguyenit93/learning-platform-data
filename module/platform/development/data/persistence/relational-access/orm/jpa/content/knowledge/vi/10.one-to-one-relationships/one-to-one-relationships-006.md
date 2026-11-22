# Đánh giá việc tải quan hệ một-một theo chuẩn và provider trong JPA

Trong **Jakarta Persistence API (JPA)**, quan hệ một-một (`@OneToOne`) biểu diễn việc một entity liên kết với tối đa một entity khác, và theo hướng ngược lại cũng chỉ liên kết với tối đa một entity. Các ví dụ phổ biến gồm tài khoản – hồ sơ, người dùng – cài đặt riêng, đơn hàng – hóa đơn, hoặc nhân viên – thẻ ra vào.

Khi viết mapping, một câu hỏi rất thực tế là: **Khi tải entity chính, JPA có tải luôn entity liên kết không?** Câu trả lời phụ thuộc vào ba yếu tố:

1. **Hợp đồng của chuẩn JPA**, đặc biệt `FetchType.EAGER` và `FetchType.LAZY`.
2. **Cấu trúc ánh xạ quan hệ**, như phía sở hữu khóa ngoại, phía `mappedBy`, khóa ngoại nullable hay shared primary key.
3. **Khả năng và cấu hình của persistence provider**, chẳng hạn Hibernate hoặc EclipseLink: proxy, bytecode enhancement, câu SQL được sinh, chiến lược batch và bộ đệm.

Bài này giải thích cách phân biệt những yếu tố trên, đọc đúng hành vi tải dữ liệu, đo số câu SQL và chủ động chọn `JOIN FETCH`, entity graph hoặc projection khi cần kiểm soát truy vấn. Không nên chỉ nhìn một annotation `fetch = LAZY` rồi kết luận rằng ứng dụng chắc chắn tiết kiệm được truy vấn.

## 1. Mô hình minh họa: Account và AccountProfile

Giả sử mỗi tài khoản có **tối đa một** hồ sơ mở rộng. Một tài khoản có thể chưa tạo hồ sơ.

```text
                       account
                  +------------------+
                  | id (PK)          |
                  | username         |
                  +------------------+
                           ^
                           |
                           | account_profile.account_id
                           | (FK, UNIQUE)
                           |
                  +-----------------------+
                  | account_profile       |
                  +-----------------------+
                  | id (PK)               |
                  | account_id (FK, UQ)   |
                  | display_name          |
                  | biography             |
                  +-----------------------+
```

Một lược đồ SQL minh họa:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE account_profile (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    biography VARCHAR(5000),
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES account(id)
);
```

Đây là DDL có tính minh họa; cách định nghĩa khóa tự sinh và một số kiểu SQL còn phụ thuộc database. Ràng buộc `UNIQUE` trên `account_id` bảo đảm **không có hai hồ sơ tham chiếu cùng một tài khoản**. `NOT NULL` ở bảng `account_profile` bảo đảm mỗi hồ sơ tham chiếu một tài khoản. Tuy nhiên, nó **không bảo đảm mỗi tài khoản đều phải có hồ sơ**; để bảo đảm điều đó phải có quy tắc nghiệp vụ và/hoặc thiết kế cơ sở dữ liệu phù hợp.

Trong Java, quan hệ có thể điều hướng từ cả hai bên:

```text
Account
    profile -------------------------> AccountProfile
           <-------------------------
                         account

Account.profile  = inverse side
Profile.account  = owning side, giữ FK account_id
```

Việc xác định phía sở hữu quan trọng vì provider có thể biết hoặc chưa biết **ID của đối tượng liên kết** tại thời điểm tải một phía của quan hệ. Chính sự khác biệt đó thường ảnh hưởng khả năng lazy load một-một.

## 2. Mapping hai chiều bằng `@OneToOne`

### 2.1. Entity Account: phía nghịch đảo

```java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "account")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String username;

    @OneToOne(
        mappedBy = "account",
        fetch = FetchType.LAZY
    )
    private AccountProfile profile;

    protected Account() {
    }

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

    public AccountProfile getProfile() {
        return profile;
    }

    public void attachProfile(AccountProfile newProfile) {
        if (newProfile == null) {
            throw new IllegalArgumentException("Profile không được null");
        }
        if (this.profile != null && this.profile != newProfile) {
            throw new IllegalStateException(
                "Tài khoản đã có hồ sơ"
            );
        }

        this.profile = newProfile;
        newProfile.attachTo(this);
    }
}
```

Từ phía `Account`:

- `@OneToOne` khai báo liên kết một-một.
- `mappedBy = "account"` trỏ tới **tên thuộc tính Java `account`** trong `AccountProfile`, không phải tên cột `account_id`.
- `Account.profile` là phía **inverse/non-owning**.
- `fetch = FetchType.LAZY` **yêu cầu theo hướng trì hoãn tải**; với JPA đây là gợi ý, không phải cam kết hiệu năng.
- Không có `@JoinColumn` trên `Account.profile` vì FK do phía `AccountProfile.account` quản lý.

Phương thức `attachProfile` là ví dụ đồng bộ hai phía khi tạo quan hệ. Trong ứng dụng thực tế cần thêm phương thức thay thế/gỡ liên kết nếu nghiệp vụ cho phép, với quy tắc rõ ràng về vòng đời hồ sơ cũ.

### 2.2. Entity AccountProfile: phía sở hữu

```java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "account_profile")
public class AccountProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true
    )
    private Account account;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Column(name = "biography", length = 5000)
    private String biography;

    protected AccountProfile() {
    }

    public AccountProfile(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Tên hiển thị rỗng");
        }
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public Account getAccount() {
        return account;
    }

    public String getDisplayName() {
        return displayName;
    }

    void attachTo(Account account) {
        this.account = account;
    }
}
```

Từ phía `AccountProfile`:

- `@JoinColumn(name = "account_id")` xác định cột FK trong bảng `account_profile`.
- `@OneToOne` trên `account` là **owning side**, vì entity này quản lý FK.
- `optional = false` tuyên bố mỗi hồ sơ phải có account.
- `nullable = false` biểu đạt ràng buộc non-null của cột FK trong schema.
- `unique = true` biểu đạt tính duy nhất của FK, giúp bảo đảm tính một-một.
- `fetch = LAZY` chỉ ra mong muốn chưa tải ngay entity `Account` khi truy vấn `AccountProfile`.

Với field access như ví dụ, JPA quản lý các field. Code nghiệp vụ vẫn nên dùng phương thức có chủ đích để đồng bộ cả `Account.profile` và `AccountProfile.account`.

### 2.3. Đọc quan hệ ngược và thuận

Hai thao tác trông đối xứng:

```java
Account account =
    entityManager.find(Account.class, 42L);

AccountProfile profile =
    entityManager.find(AccountProfile.class, 100L);
```

Nhưng **khả năng lazy load của `account.getProfile()` có thể khác `profile.getAccount()`**, bởi FK chỉ được lưu ở một phía.

Ta sẽ phân tích lý do sau khi làm rõ hợp đồng JPA.

## 3. Chuẩn JPA quy định gì về EAGER và LAZY?

### 3.1. `@OneToOne` mặc định là EAGER

Trong JPA, thuộc tính `fetch` của `@OneToOne` có mặc định là:

```java
@OneToOne(fetch = FetchType.EAGER)
private AccountProfile profile;
```

Viết:

```java
@OneToOne
private AccountProfile profile;
```

tương đương với việc dùng **EAGER mặc định** đối với yêu cầu tải quan hệ.

Vì vậy, nếu entity có nhiều quan hệ một-một và chỉ ghi `@OneToOne`, tải entity chính có thể kéo theo nhiều entity liên kết ngay cả khi nghiệp vụ chưa cần sử dụng chúng.

### 3.2. EAGER là yêu cầu tải, không phải yêu cầu JOIN

Theo ngữ nghĩa JPA:

- **`FetchType.EAGER`:** provider phải nạp dữ liệu liên quan một cách eager theo hợp đồng fetch của mapping.
- **`FetchType.LAZY`:** provider *được phép* trì hoãn lấy dữ liệu đến khi cần, nhưng không bắt buộc phải làm vậy.

Một hiểu nhầm thường gặp:

> “`EAGER` nghĩa là luôn có đúng một câu SQL dùng `JOIN`.”

Không đúng. Provider có thể hoàn thành yêu cầu EAGER bằng:

```sql
-- Cách A: một câu SQL JOIN.
SELECT a.id, a.username,
       p.id AS profile_id, p.display_name
FROM account a
LEFT JOIN account_profile p
       ON p.account_id = a.id
WHERE a.id = ?;
```

Hoặc:

```sql
-- Cách B: nhiều câu SQL.
SELECT a.id, a.username
FROM account a
WHERE a.id = ?;

SELECT p.id, p.account_id, p.display_name
FROM account_profile p
WHERE p.account_id = ?;
```

Cả hai hướng đều có thể đáp ứng nhu cầu dữ liệu EAGER. Số câu lệnh, cách JOIN hay SELECT bổ sung là **chi tiết chiến lược của provider** và loại truy vấn được sử dụng.

### 3.3. LAZY chỉ là gợi ý

Khi viết:

```java
@OneToOne(fetch = FetchType.LAZY)
private AccountProfile profile;
```

ứng dụng nói với JPA: “Tôi muốn chỉ tải quan hệ khi truy cập nó, nếu cơ chế của provider cho phép”.

Nhưng chuẩn **không bảo đảm** rằng:

- Chắc chắn không có SQL liên quan khi tải entity cha.
- Không có SELECT phụ để kiểm tra đối tượng liên kết có tồn tại hay không.
- Getter `getProfile()` luôn có thể chạy sau khi persistence context đã đóng.
- Tất cả provider dùng cùng số câu truy vấn.
- Một phiên bản provider sẽ thực thi LAZY giống phiên bản khác.

Do đó, **annotation LAZY chưa phải bằng chứng rằng quan hệ được tải lazy**. Cần quan sát SQL thực tế trong cấu hình dự án.

### 3.4. Bảng hợp đồng JPA và điều cần kiểm chứng

| Cấu hình | Điều chuẩn diễn đạt | Điều phải đo/kiểm tra trong provider |
|---|---|---|
| `@OneToOne` không có `fetch` | EAGER mặc định | JOIN hay các SELECT riêng? |
| `@OneToOne(fetch = EAGER)` | Yêu cầu tải eager | Có bao nhiêu statement, bao nhiêu cột? |
| `@OneToOne(fetch = LAZY)` | Gợi ý trì hoãn | Provider có honor LAZY không? |
| EAGER trên inverse side | Vẫn là EAGER theo mapping | Có SELECT kiểm tra tồn tại không? |
| LAZY trên owning side | Gợi ý trì hoãn từ entity chứa FK | Có proxy/enhancement, có nạp sớm không? |
| LAZY trên inverse side | Gợi ý trì hoãn từ entity không chứa FK | Provider có xác định được null/non-null mà không SELECT không? |
| `optional = false` | Association phải hiện hữu theo mô hình | Có tối ưu truy vấn không? DB có thực sự bảo đảm tồn tại không? |
| `@MapsId` | Identity dẫn xuất từ liên kết | Provider có tận dụng ID chung để tải lazy không? |

Các hành vi bên phải **không thể suy ra chỉ bằng việc đọc một annotation**.

## 4. Vì sao phía sở hữu và phía `mappedBy` có thể tải khác nhau?

### 4.1. Phía sở hữu có khóa ngoại trong hàng vừa đọc

Xét:

```text
account_profile
+-----+------------+---------------+
| id  | account_id | display_name  |
+-----+------------+---------------+
| 100 | 42         | "An Nguyễn"  |
+-----+------------+---------------+
```

Khi provider đọc row này, nó đã biết:

```text
AccountProfile.id = 100
AccountProfile.account_id = 42
```

Do vậy, nếu cấu hình và provider hỗ trợ, nó **có thể** tạo một proxy/đại diện trì hoãn cho `Account(id = 42)` mà chưa cần chạy truy vấn lấy đầy đủ row `account`.

Một diễn biến khả dĩ:

```text
find(AccountProfile, 100)
        |
        v
SELECT ... FROM account_profile WHERE id = 100
        |
        v
Profile managed, biết account_id = 42
        |
        v
profile.getAccount() -> reference đến Account(42)
        |
        | Khi truy cập dữ liệu Account chưa có
        v
SELECT ... FROM account WHERE id = 42
```

Đây là khả năng thực thi tương đối thuận lợi cho **owning-side to-one lazy loading**. Tuy vậy, provider có thể phải nạp sớm vì thiếu proxy phù hợp, cấu hình enhancement hoặc các quy tắc fetch khác.

### 4.2. Phía inverse không có FK ở row của nó

Khi provider đọc:

```text
account
+----+-----------+
| id | username  |
+----+-----------+
| 42 | "an42"    |
+----+-----------+
```

chỉ từ row này, nó **chưa biết**:

- Có `AccountProfile` nào tham chiếu `Account(42)` hay không?
- Nếu có, `AccountProfile.id` là giá trị nào?

Vì FK nằm ở bảng `account_profile`, provider có thể phải chạy một câu SQL để xác định:

```sql
SELECT p.id, p.account_id
FROM account_profile p
WHERE p.account_id = 42;
```

Nếu tìm thấy kết quả, provider có thể khởi tạo reference thích hợp hoặc tải profile. Nếu không tìm thấy, property `Account.profile` phải thể hiện tình huống `null` theo ngữ nghĩa association optional.

Đây là **vấn đề kiểm tra sự tồn tại** (*existence check*) của phía inverse.

Một kịch bản phổ biến:

```text
find(Account, 42)
       |
       v
SELECT ... FROM account WHERE id = 42
       |
       v
Provider cần biết profile có tồn tại?
       |
       +-----> SELECT ... FROM account_profile WHERE account_id = 42
       |
       v
Account.profile có thể = null hoặc tham chiếu đến profile
```

Ngay cả khi code chưa gọi `account.getProfile()`, câu SELECT kiểm tra có thể đã xảy ra. Điều này giải thích vì sao **LAZY ở phía `mappedBy` thường khó tối ưu hơn phía FK owner**, đặc biệt trong cấu trúc FK unique tách ID.

### 4.3. `optional = false` có giúp bỏ truy vấn kiểm tra không?

Ví dụ:

```java
@OneToOne(
    mappedBy = "account",
    fetch = FetchType.LAZY,
    optional = false
)
private AccountProfile profile;
```

`optional = false` diễn đạt rằng **association được yêu cầu hiện hữu**. Một số provider hoặc cấu hình có thể tận dụng thông tin này để tránh một phần kiểm tra null, sử dụng proxy hoặc tối ưu chiến lược nạp.

Nhưng cần phân biệt:

1. `optional = false` là **thông tin mapping/hợp đồng mô hình**.
2. Trong sơ đồ FK ở phía `account_profile`, ràng buộc FK và `NOT NULL` ở đó chỉ bảo đảm **mỗi profile có account**.
3. Chúng **không bảo đảm mỗi account có profile**.
4. Nếu thực tế có `Account` chưa có profile, khai báo `optional = false` ở phía inverse không còn phản ánh dữ liệu thật.
5. Provider có thể hoặc không tận dụng khai báo này; không có cam kết một câu SQL hoặc zero extra SELECT theo JPA.

Vì vậy, **đừng đổi `optional` sang false chỉ với mục đích “làm lazy nhanh hơn” khi quan hệ thật sự optional**. Đó là cách làm sai mô hình nghiệp vụ để đổi lấy một tối ưu không được bảo đảm.

### 4.4. Có thể khắc phục bằng proxy không?

Proxy thường cần một identity để đại diện cho entity liên kết. Phía owner biết FK nên có một ứng viên ID của entity đích. Phía inverse với FK unique trong bảng đích lại không biết ngay primary key của profile, khiến việc tạo proxy khó hơn.

Provider có thể dùng:

- Truy vấn kiểm tra tồn tại và tìm ID.
- Bytecode enhancement để trì hoãn access ở mức attribute.
- Lazy interception trên entity.
- Một số chiến lược riêng cho shared primary key.
- Kết hợp cache, join hoặc batch fetch.

Các giải pháp trên phụ thuộc provider/phiên bản/cấu hình. Không nên coi sự tồn tại của proxy trong một thử nghiệm đơn lẻ là chứng cứ cho mọi mapping một-một.

## 5. Hibernate, EclipseLink và giới hạn portable

### 5.1. Hibernate: proxy và bytecode enhancement

Hibernate có thể hỗ trợ lazy loading bằng **proxy** hoặc **bytecode enhancement**. Hai cơ chế có vai trò khác nhau:

- **Proxy:** một đối tượng đại diện cho entity liên kết, có thể được khởi tạo đầy đủ khi dữ liệu cần truy cập.
- **Bytecode enhancement:** provider bổ sung cơ chế theo dõi/chặn truy cập bằng cách tăng cường bytecode class, cho phép một số hình thức lazy attribute loading mà proxy truyền thống khó thực hiện.

Với `@OneToOne`, nhất là phía inverse, hành vi phụ thuộc nhiều vào:

- Phiên bản Hibernate.
- Cách entity được tạo/tăng cường bytecode.
- Chiều quan hệ, ID có chung nhau hay không.
- `optional`, nullable của FK và tính chính xác của dữ liệu.
- Fetch plan ở câu truy vấn.
- Việc entity đích đã có trong persistence context hoặc cache.
- Khả năng tạo proxy cho class đích.

Một số phiên bản và cách cấu hình Hibernate trong lịch sử cần thiết lập enhancement hoặc annotation riêng để đạt lazy loading tốt hơn cho một-một phía inverse. Không nên sao chép nguyên một mẹo riêng từ phiên bản khác mà không xác nhận với Hibernate version của dự án hiện tại.

**Kết luận thực dụng:** Nếu đang dùng Hibernate, hãy xác nhận cấu hình bytecode enhancement và quan sát SQL khi load **cả phía owner lẫn phía inverse**. Chỉ nhìn `fetch = LAZY` chưa đủ.

### 5.2. EclipseLink: weaving và indirection

EclipseLink có cơ chế **weaving** và **indirection** để hỗ trợ deferred/lazy loading. Mức độ hoạt động của một-một cũng có thể phụ thuộc:

- Weaving được bật ở thời gian build hay runtime.
- Tương thích class loading/container.
- Mapping và tùy chọn indirection cụ thể.
- Khả năng xác định association tại thời điểm tải entity chính.

Như với Hibernate, **không suy ra mọi phía inverse đều lazy hoặc mọi default đều cùng số SQL**. Hãy xác nhận bằng SQL logging và thiết lập chính xác của EclipseLink được sử dụng.

### 5.3. Vì sao không nên viết tài liệu kiểu “Hibernate luôn…”?

Ví dụ câu khẳng định:

> “Hibernate sẽ luôn tải `@OneToOne(mappedBy = ...)` bằng một SELECT riêng.”

là khái quát quá mức. Cấu hình enhancement, shared primary key, phiên bản Hibernate, entity graph, JOIN FETCH, cache và trạng thái persistence context có thể làm kết quả khác.

Câu đúng hơn là: **“Với nhiều mapping một-một inverse dùng FK unique ở bảng con, provider có thể phải kiểm tra sự tồn tại bằng SELECT riêng; muốn biết chắc phải đo trong cấu hình cụ thể.”**

Chính sự phân biệt này là trọng tâm khi **đánh giá theo chuẩn và provider**.

## 6. Ba kiểu lưu quan hệ một-một và ảnh hưởng tải dữ liệu

Một-một có thể được ánh xạ theo nhiều cấu trúc quan hệ. Cùng dùng `@OneToOne` nhưng cơ hội trì hoãn tải sẽ khác nhau.

### 6.1. Kiểu A: FK unique ở bảng phụ

Sơ đồ đang dùng:

```text
account(id)
account_profile(id, account_id UNIQUE FK)
```

Ưu điểm:

- Hai entity có ID độc lập.
- Có thể tạo account trước rồi tạo profile sau.
- Có thể cho phép account không có profile.

Điểm cần đánh giá:

- Từ profile tới account, FK có sẵn trong row profile.
- Từ account tới profile, phải xác định profile có tồn tại và ID là gì.
- Inverse LAZY có thể phát sinh SELECT kiểm tra hoặc tải sớm.

### 6.2. Kiểu B: shared primary key với `@MapsId`

Có thể thiết kế profile có **ID chính bằng ID của account**:

```text
account
+--------------------+
| id (PK)            |
+--------------------+
         ^
         |
         | same value
         |
account_profile
+--------------------+
| id (PK, FK)        |
+--------------------+
```

Một cách ánh xạ:

```java
@Entity
@Table(name = "account")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String username;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private AccountProfile profile;

    protected Account() {
    }
}
```

```java
@Entity
@Table(name = "account_profile")
public class AccountProfile {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Account account;

    private String displayName;

    protected AccountProfile() {
    }
}
```

`@MapsId` nói rằng khóa chính của `AccountProfile` lấy từ association `account`. Cấu trúc này thường phù hợp với hồ sơ có vòng đời gắn chặt với account.

**Tác động với LAZY:** Khi tải `Account(id = 42)`, provider biết nếu profile tương ứng tồn tại thì ID của nó cũng là 42. Điều này có thể đơn giản hóa việc tạo reference đến entity liên kết. Nhưng **nếu profile là optional**, provider vẫn cần xử lý đúng trường hợp không có row profile. Biết **ID có thể có** không đồng nghĩa biết **row chắc chắn tồn tại**.

Do đó shared primary key **có thể thuận lợi hơn cho một số chiến lược lazy**, nhưng không phải cam kết portable rằng sẽ không có extra SELECT. Hãy kiểm tra cả trường hợp có và không có profile.

### 6.3. Kiểu C: FK ở bảng Account

Ngược lại, có thể đặt FK trong bảng account:

```text
account(id, profile_id UNIQUE FK)
account_profile(id)
```

Ví dụ:

```java
@Entity
public class Account {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", unique = true)
    private AccountProfile profile;

    protected Account() {
    }
}
```

Ở đây `Account.profile` là owning side. Ngay khi tải account, provider có thể đọc `profile_id` từ cùng row để biết target ID hoặc biết `null`. Điều này thuận lợi cho việc dùng proxy hoặc không cần truy vấn khi profile chưa tồn tại.

Nhưng đảo chiều FK là một **quyết định về thiết kế schema và nghiệp vụ**, không chỉ “mẹo tăng tốc”. Với database đã có dữ liệu, thay đổi chiều FK đòi hỏi migration, chuyển dữ liệu, unique constraint, xử lý null và cập nhật toàn bộ mapping.

### 6.4. Bảng so sánh ba cấu trúc

| Cấu trúc | Từ Account có biết target ID ngay không? | Cần lưu ý khi lazy |
|---|---|---|
| FK unique ở `account_profile.account_id`, ID profile độc lập | Thường **không** | Inverse side có thể cần SELECT để biết tồn tại/ID |
| Shared PK, `account_profile.id = account.id` | Biết **ID tiềm năng** | Vẫn cần xử lý trường hợp profile không tồn tại |
| FK `account.profile_id` trên Account | **Có** nếu FK non-null; biết null nếu FK null | Dễ hình thành proxy/không truy vấn hơn trong một số provider |
| Join table một-một | Chưa chắc, phải tìm row trong bảng nối | Có thể cần join/SELECT tùy mapping |

Đây là phân tích khả năng cung cấp thông tin cho provider; **không phải bảng bảo đảm số câu SQL**.

## 7. Đọc SQL để biết quan hệ đang được tải thế nào

### 7.1. Trường hợp một câu SQL

Một truy vấn tìm account có thể sinh:

```sql
SELECT
    a.id,
    a.username,
    p.id AS profile_id,
    p.account_id,
    p.display_name
FROM account a
LEFT JOIN account_profile p
    ON p.account_id = a.id
WHERE a.id = ?;
```

Câu truy vấn này đưa cả account và profile vào một result set. Với profile optional, `LEFT JOIN` giữ account ngay cả khi profile không tồn tại.

Điều này có thể xảy ra nếu:

- Association EAGER và provider chọn join.
- Query dùng `LEFT JOIN FETCH` tường minh.
- Entity graph/fetch plan khiến provider chọn join.
- Provider có chiến lược eager riêng.

### 7.2. Trường hợp hai câu SQL

```sql
SELECT a.id, a.username
FROM account a
WHERE a.id = ?;

SELECT p.id, p.account_id, p.display_name
FROM account_profile p
WHERE p.account_id = ?;
```

Câu thứ hai có thể là:

- Phần hoàn tất một association EAGER.
- Phần kiểm tra tồn tại trên inverse side.
- Lần lazy-load khi code truy cập `getProfile()`.
- Một truy vấn khác do fetch plan/provider thực hiện.

**Chỉ nhìn thấy SELECT thứ hai không đủ kết luận lazy đã hoạt động hay thất bại.** Cần biết nó diễn ra **trước hay sau khi ứng dụng truy cập association**, và entity/persistence context đang ở trạng thái nào.

### 7.3. Trường hợp không có SELECT cho profile

```sql
SELECT a.id, a.username
FROM account a
WHERE a.id = ?;
```

Nếu ứng dụng không đụng đến profile và không có truy vấn tiếp theo liên quan, đó là dấu hiệu provider có thể đang trì hoãn đúng nội dung cần tải. Nhưng để xác nhận:

1. Tạo một persistence context mới.
2. Kiểm tra profile có thực sự chưa nằm trong cache/context.
3. Thử truy cập `getProfile()` và các thuộc tính của profile.
4. Quan sát liệu SQL xuất hiện khi nào.
5. Làm lại với trường hợp account có profile và account không có profile.

Đối với một reference/proxy, **gọi getter lấy reference** đôi khi không làm SQL; truy cập một thuộc tính chưa biết của entity đích mới khởi tạo proxy. Vì vậy cần thiết kế điểm truy cập trong thử nghiệm đủ rõ.

## 8. N+1 với quan hệ một-một

### 8.1. N+1 không chỉ xảy ra ở collection

Giả sử cần hiển thị 100 account:

```java
List<Account> accounts =
    entityManager.createQuery(
        "select a from Account a order by a.id",
        Account.class
    ).getResultList();

for (Account account : accounts) {
    System.out.println(account.getUsername());
}
```

Với một số cấu hình tải một-một ở phía inverse, provider có thể sinh:

```text
1 SELECT lấy 100 Account
+ 100 SELECT tìm/tải AccountProfile theo account_id
= khoảng 101 SELECT
```

Ngay cả khi vòng lặp **chỉ đọc username**, sự cần thiết kiểm tra profile hoặc hoàn thành fetch EAGER có thể phát sinh truy vấn phụ, tùy mapping/provider. Nếu thuộc tính LAZY được thực thi thực sự và không ai truy cập profile, kết quả có thể chỉ là một truy vấn.

Không nên xem con số 101 là quy luật cố định. Cache, join fetching, batch loading, shared key, enhancement và provider khác có thể thay đổi số câu SQL.

### 8.2. Vì sao số truy vấn quan trọng?

Một câu query chạy nhanh trong môi trường development chưa chắc cho kết quả tốt khi có:

- 1.000 tài khoản thay vì 10.
- Độ trễ giữa application server và database.
- Nhiều người dùng đồng thời.
- Profile có trường LOB hay quan hệ khác.
- Áp lực connection pool và transaction.
- Query timeout hoặc tải CPU database.

Ví dụ giả định, không phải benchmark đo được:

```text
Latency mạng trung bình cho mỗi round trip: 4 ms

1 SELECT + 100 SELECT phụ
≈ 101 round trip * 4 ms
≈ 404 ms chỉ riêng độ trễ mạng (chưa tính thực thi SQL)

1 SELECT có JOIN thích hợp
≈ 1 round trip * 4 ms
≈ 4 ms phần round trip
```

Đây chỉ là minh họa mức độ ảnh hưởng của round trip; join cũng có thể tốn CPU, I/O, tạo result set lớn hoặc không được optimizer xử lý tối ưu trong mọi trường hợp. Vì thế **giảm số SELECT thường có lợi nhưng vẫn cần đo thời gian và khối lượng dữ liệu thực tế**.

### 8.3. EAGER không bảo vệ khỏi N+1

Khi EAGER được đáp ứng bằng SELECT riêng sau truy vấn gốc, mỗi entity có thể kéo theo một truy vấn đến đối tượng liên kết. Vì vậy:

> **EAGER nghĩa là yêu cầu dữ liệu được tải, không phải bảo đảm tránh N+1.**

Muốn yêu cầu truy vấn lấy cả hai entity theo một hướng cụ thể, thường cần **query fetch plan** rõ ràng hơn.

## 9. Chủ động tải bằng JPQL JOIN FETCH

### 9.1. Tải cả account và profile khi thật sự cần

Ví dụ màn hình chi tiết tài khoản luôn hiển thị profile:

```java
List<Account> accounts = entityManager.createQuery(
    """
    select a
    from Account a
    left join fetch a.profile
    where a.id in :ids
    """,
    Account.class
)
.setParameter("ids", List.of(42L, 43L, 44L))
.getResultList();
```

`LEFT JOIN FETCH` yêu cầu JPA tải association `a.profile` cùng kết quả query. Nó hợp lý khi một số account có thể chưa có profile.

Cần phân biệt:

- `LEFT JOIN FETCH`: giữ account không có profile.
- `JOIN FETCH` hoặc `INNER JOIN FETCH`: chỉ giữ account có profile theo điều kiện join.
- `JOIN` thông thường không có `FETCH`: cho phép join để lọc/chọn dữ liệu, **không mặc nhiên** yêu cầu khởi tạo association trên entity trả về.

Ví dụ nguy hiểm nếu profile optional:

```java
// Account không có profile sẽ bị loại khỏi kết quả.
select a
from Account a
join fetch a.profile
```

Nếu yêu cầu nghiệp vụ là “liệt kê tất cả account, kể cả account chưa có profile”, phải dùng `left join fetch` hoặc cách khác giữ row gốc.

### 9.2. Vì sao JOIN FETCH hiệu quả với một-một?

Với một-một đúng nghĩa ở DB, mỗi account liên kết tối đa một profile. Một `LEFT JOIN` thường không nhân bản account thành nhiều row như fetch join collection một-nhiều, nên việc fetch join một-một thường dễ kiểm soát hơn về số row.

Tuy nhiên cần lưu ý:

- Database phải có ràng buộc uniqueness phù hợp; dữ liệu sai có thể làm kết quả bất ngờ.
- Fetch join nhiều quan hệ khác nhau có thể mở rộng số cột, ảnh hưởng lượng dữ liệu truyền.
- Một query có nhiều join có thể có kế hoạch thực thi tốn kém.
- Nếu chỉ cần vài cột đơn giản, **DTO projection** có thể tốt hơn việc hydrate hai entity.
- Không dùng fetch join như mặc định cho mọi use case chỉ vì muốn tránh N+1.

### 9.3. Entity query và danh sách trả về

Một ví dụ truy vấn danh sách có phân trang:

```java
List<Account> page = entityManager.createQuery(
    """
    select a
    from Account a
    left join fetch a.profile
    order by a.id
    """,
    Account.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
```

Với quan hệ một-một, thông thường không có sự nhân bản row lớn do collection fetch như một-nhiều. Dù vậy, cần xét các quan hệ fetch khác và SQL thực tế; không suy ra rằng mọi truy vấn có `JOIN FETCH` đều phân trang hiệu quả. Nếu thêm fetch join collection, provider có thể phải xử lý pagination đặc biệt hoặc có cảnh báo.

### 9.4. Nếu không cần profile, không fetch profile

Trường hợp trang danh sách chỉ hiển thị username:

```java
select a
from Account a
order by a.username
```

Muốn tối ưu, cần bảo đảm các quan hệ không bị tải sớm không cần thiết. Có thể cân nhắc lazy mapping, entity graph phù hợp hoặc **trả DTO chỉ gồm các cột cần dùng**. Việc chủ động fetch profile trên mọi truy vấn danh sách đi ngược mục tiêu giảm I/O khi màn hình không sử dụng dữ liệu đó.

## 10. Entity graph: chỉ định fetch plan theo use case

JPA cung cấp **entity graph** để diễn đạt nhu cầu tải association mà không phải thay đổi mapping toàn cục.

### 10.1. Khai báo named graph

```java
import jakarta.persistence.Entity;
import jakarta.persistence.NamedAttributeNode;
import jakarta.persistence.NamedEntityGraph;

@Entity
@NamedEntityGraph(
    name = "Account.withProfile",
    attributeNodes = @NamedAttributeNode("profile")
)
public class Account {
    // id, username, @OneToOne(mappedBy="account") profile...
}
```

Ở truy vấn cần profile:

```java
var graph = entityManager
    .getEntityGraph("Account.withProfile");

List<Account> accounts = entityManager.createQuery(
    "select a from Account a where a.id in :ids",
    Account.class
)
.setParameter("ids", List.of(42L, 43L))
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
```

Graph diễn đạt yêu cầu tải `profile` cho query này. Nhưng nó **không bảo đảm** provider dùng một câu SQL với `JOIN`. Provider có thể lựa chọn cách tải hợp lệ với fetch graph và chiến lược nội bộ.

### 10.2. Phân biệt fetch graph và load graph

Hai hint thường dùng:

| Hint | Ngữ nghĩa chung |
|---|---|
| `jakarta.persistence.fetchgraph` | Những attribute trong graph được xem là cần eager fetch; những attribute khác được xem theo lazy semantics của fetch graph, với ngoại lệ provider có thể lấy thêm state |
| `jakarta.persistence.loadgraph` | Attribute trong graph được tải eager; những attribute không nằm trong graph giữ fetch policy theo mapping |

Với `loadgraph`, một quan hệ `@OneToOne` khai báo EAGER mà không có trong graph vẫn có thể được tải theo mapping mặc định. Với `fetchgraph`, ý định có thể là không lấy các association ngoài graph ngay, nhưng **không được coi đây là bảo đảm SQL tối thiểu trong mọi provider**.

Nên dùng graph khi nhiều use case cần tập association khác nhau, muốn tách chiến lược tải khỏi entity mapping, và có nhu cầu thay đổi query fetch plan rõ ràng.

### 10.3. Fetch graph không sửa lỗi thiết kế quan hệ

Nếu JPA mapping nhầm chiều FK, thiếu `mappedBy`, thiếu unique constraint hoặc liên kết hai chiều không nhất quán, entity graph không tự sửa được. Nó chỉ điều chỉnh chiến lược **tải** một mô hình đã được ánh xạ.

## 11. DTO projection khi chỉ cần vài cột

Một màn hình báo cáo có thể chỉ cần:

- ID tài khoản.
- Username.
- Tên hiển thị trong profile nếu có.

Không cần thiết phải tạo các managed entity `Account` và `AccountProfile` chỉ để trả ba trường.

### 11.1. DTO dạng record

```java
package com.example.api;

public record AccountSummary(
    Long id,
    String username,
    String displayName
) { }
```

### 11.2. Constructor projection

```java
List<AccountSummary> summaries =
    entityManager.createQuery(
        """
        select new com.example.api.AccountSummary(
            a.id,
            a.username,
            p.displayName
        )
        from Account a
        left join a.profile p
        order by a.id
        """,
        AccountSummary.class
    ).getResultList();
```

`LEFT JOIN` giữ account chưa có profile; `displayName` có thể là `null` cho account đó.

Điểm khác biệt:

- Câu query chọn **dữ liệu cần thiết**, không bắt buộc hydrate toàn bộ entity.
- `AccountSummary` là DTO Java, không được JPA quản lý dưới dạng entity.
- Đổi trường DTO không kích hoạt dirty checking hay SQL update.
- Truy vấn không cần lấy biography lớn hoặc các association khác khi chúng không được select.

Đây thường là lựa chọn rõ nghĩa nhất cho API danh sách, báo cáo hoặc giao diện chỉ cần vài cột.

**Phân biệt `JOIN` và `JOIN FETCH`:** Constructor projection dùng `left join a.profile p` để tham chiếu trường của profile; nó **không cần** `fetch` vì kết quả cần trả là DTO, không phải entity graph có association được khởi tạo.

## 12. Thử nghiệm tải dữ liệu đúng cách trong dự án

Để đánh giá `@OneToOne` theo provider, cần một phép thử có thể phân biệt **SQL xuất hiện khi tải entity** và **SQL chỉ xuất hiện khi truy cập association**.

### 12.1. Chuẩn bị hai tình huống dữ liệu

Tạo tối thiểu:

```text
Account #1: có AccountProfile
Account #2: không có AccountProfile
```

Ở mapping FK unique tách ID, hai tình huống này đặc biệt quan trọng vì phía inverse phải xử lý cả trường hợp liên kết tồn tại và `null`.

Nếu mapping khai báo `optional = false` ở cả hai phía, dữ liệu phải thật sự tuân thủ quy tắc đó; không cố tạo dữ liệu sai chỉ để đo hiệu năng.

### 12.2. Đặt các điểm quan sát

Một phép thử theo ý tưởng:

```java
Account account = entityManager.find(Account.class, accountId);

// Mốc A: kiểm tra các SQL đã chạy đến đây.

// Nếu provider có proxy/attribute lazy:
AccountProfile profile = account.getProfile();

// Mốc B: kiểm tra sau khi lấy reference.
if (profile != null) {
    String displayName = profile.getDisplayName();
}

// Mốc C: kiểm tra sau khi đọc dữ liệu của profile.
```

Ở từng mốc, ghi nhận **số và loại câu SQL**. Phải phân biệt:

- `getProfile()` trả về proxy, chưa tải row.
- `getProfile()` tự kích hoạt SELECT để xác định tồn tại.
- `getDisplayName()` kích hoạt tải nội dung profile.
- Provider đã tải profile ngay trong `find()`.
- Truy vấn không phát SQL do entity đã có trong first-level cache.

### 12.3. Tạo persistence context mới để tránh kết quả bị che

Nếu trước đó đã tải `AccountProfile` hoặc `Account` vào cùng persistence context, JPA có thể sử dụng entity đã managed. Khi đó phép đo có thể trả 0 truy vấn phụ không phải vì fetch tối ưu mà vì dữ liệu đã có sẵn.

Trong môi trường kiểm thử, có thể dùng `EntityManager` mới cho từng kịch bản hoặc làm mới state theo cách phù hợp. Nếu dùng cache cấp hai, cần kiểm soát cache để phép đo phản ánh đúng mục tiêu.

Không phải lúc nào cũng cần tắt cache trong production; mục đích ở đây là **đo một trạng thái đã biết**, không vô tình kết luận từ cache-hit.

### 12.4. Không đo sau khi transaction/context đã đóng nếu muốn quan sát lazy loading

Nếu entity đã detached hoặc persistence context đóng trước khi truy cập association LAZY, provider có thể không thể tải dữ liệu và ném exception (ví dụ các ngoại lệ lazy initialization riêng của provider).

Điều đó không chứng minh mapping sai. Nó chứng minh **dữ liệu cần lazy load không còn có ngữ cảnh persistence thích hợp**.

Hãy đo cả truy cập trong transaction/persistence context còn hoạt động và kiểm tra DTO được tạo trước khi trả về API.

### 12.5. Theo dõi query log của provider

Với Hibernate, các kỹ thuật thường dùng gồm:

- Bật log SQL, ví dụ category `org.hibernate.SQL`.
- Bật log bind parameter tương ứng với phiên bản Hibernate.
- Bật Hibernate statistics, nếu cần đếm số prepare statement.
- Dùng `StatementInspector` hoặc datasource-proxy/P6Spy khi dự án hỗ trợ.
- Quan sát trace của một request cụ thể và transaction tương ứng.

Ví dụ cấu hình mang tính định hướng cho Hibernate:

```properties
hibernate.generate_statistics=true
```

Một đoạn đếm số statement qua API Hibernate (không thuộc JPA chuẩn):

```java
org.hibernate.SessionFactory sessionFactory =
    entityManagerFactory.unwrap(
        org.hibernate.SessionFactory.class
    );

var stats = sessionFactory.getStatistics();
long before = stats.getPrepareStatementCount();

// Thực hiện thao tác JPA cần quan sát.

long after = stats.getPrepareStatementCount();
long preparedStatements = after - before;
```

Ví dụ này phụ thuộc Hibernate. Nếu application chạy đồng thời nhiều request, thống kê toàn cục có thể bao gồm câu SQL của request khác. Để kiểm thử chính xác, cần cô lập workload hoặc quan sát SQL per transaction/request.

Không đồng nhất **prepared statement count** với thời gian thực thi, số round trip mạng hoặc số dòng truy vấn trả về. Cần số liệu khác nếu muốn đánh giá toàn diện.

### 12.6. EclipseLink và provider khác

Với EclipseLink, dùng cấu hình logging/query monitoring và thống kê tương ứng theo phiên bản, chú ý weaving có hoạt động thật không. Không dùng các API riêng của Hibernate để suy luận về hành vi EclipseLink.

Một kết quả so sánh có giá trị cần ghi rõ:

```text
Provider:
Provider version:
JPA/Jakarta Persistence version:
Database + driver:
Enhancement/weaving:
Mapping (owner/inverse/shared PK):
optional:
FetchType:
Query (find/JPQL/fetch join/entity graph):
Cache state:
Số SELECT trước access:
Số SELECT sau access:
Dữ liệu có/không có profile:
```

Nếu thiếu những thông tin này, hai kết quả khác nhau có thể cùng đúng trong hai môi trường khác nhau.

## 13. Dùng `PersistenceUnitUtil.isLoaded` để quan sát trạng thái tải

Jakarta Persistence có API kiểm tra trạng thái tải:

```java
var persistenceUtil =
    entityManager.getEntityManagerFactory()
                 .getPersistenceUnitUtil();

Account account = entityManager.find(Account.class, accountId);

boolean profileLoaded =
    persistenceUtil.isLoaded(account, "profile");
```

API này giúp hỏi provider xem attribute `profile` được coi là loaded hay chưa. Có thể dùng để quan sát trước và sau khi truy cập association.

Nhưng cũng cần lưu ý:

- Kết quả là trạng thái tải theo góc nhìn JPA/provider, không phải **số câu SQL**.
- Một association có proxy có thể có nhiều mức “đã có reference” và “đã khởi tạo state đích”, tùy provider.
- Một entity có thể đã loaded nhờ join, secondary select hoặc cache.
- Không dùng `isLoaded` một mình để kết luận hiệu năng.

Nên kết hợp **trạng thái tải + SQL log + dữ liệu truy cập thực tế**.

## 14. Khi nào cần batch loading hoặc provider-specific tuning?

Đối với màn hình có hàng trăm entity và association tải từng đối tượng, một số provider hỗ trợ **batch fetching** để nhóm nhiều lần tải association thành ít truy vấn hơn.

Trong Hibernate, có các cơ chế như:

- Batch fetching theo cấu hình provider.
- `@BatchSize`, annotation riêng của Hibernate.
- Các thiết lập kích thước batch mặc định.
- Bytecode enhancement cho lazy attribute.
- Fetch profile hoặc các tiện ích fetch plan khác của Hibernate.

Tuy nhiên:

1. Đây **không phải mọi API đều thuộc JPA chuẩn**.
2. Không phải mọi mapping một-một, đặc biệt phía inverse, đều có hiệu quả batch giống nhau.
3. Kích thước batch quá lớn cũng có thể gây truy vấn `IN` cồng kềnh hoặc tốn tài nguyên.
4. Provider có thể thay đổi cách triển khai qua các phiên bản.
5. Batch fetching thường giúp giảm N+1, nhưng không nhất thiết hiệu quả hơn một projection hoặc fetch join đúng use case.

Nếu ứng dụng chủ yếu đọc danh sách metadata, DTO projection thường giải quyết nhu cầu rõ ràng hơn so với cố làm lazy từng association bằng nhiều tùy chọn riêng của provider.

## 15. Tính nhất quán của quan hệ và tác động khi tải

### 15.1. Owning side và inverse side ảnh hưởng việc ghi liên kết

Trong ví dụ:

```java
// Owning side.
profile.attachTo(account);

// Inverse side.
account.attachProfile(profile);
```

Nếu chỉ sửa `account.profile` nhưng quên `profile.account`, JPA có thể không ghi FK như mong muốn, vì `profile.account` quản lý liên kết SQL.

Điều đó là **vấn đề cập nhật relationship**, khác với **vấn đề fetch plan**. Không nên gộp hai nguyên nhân thành một khi debug.

### 15.2. Cascade không quyết định kiểu fetch

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    fetch = FetchType.LAZY
)
private AccountProfile profile;
```

- `cascade = ALL` ảnh hưởng việc truyền các thao tác lifecycle như persist/merge/remove.
- `fetch = LAZY` diễn đạt mong muốn tải trì hoãn.
- `mappedBy` đánh dấu inverse side.

Ba yếu tố **độc lập về mục đích**. Cascade ALL không biến inverse side thành owner, và cũng không tự biến LAZY thành EAGER.

### 15.3. Orphan removal không quyết định fetch

```java
@OneToOne(
    mappedBy = "account",
    orphanRemoval = true
)
private AccountProfile profile;
```

`orphanRemoval` biểu đạt quy tắc xóa entity phụ khi bị loại khỏi quan hệ sở hữu vòng đời, theo mapping và transaction. Nó **không bảo đảm** profile được tải lazily hay eagerly.

### 15.4. `optional` và nullable phải phản ánh dữ liệu thật

```java
@OneToOne(optional = false)
@JoinColumn(nullable = false)
private Account account;
```

Ở phía owner `AccountProfile.account`, non-nullable FK có thể được bảo vệ bởi schema. Nhưng ở inverse `Account.profile`, không có cột FK tương ứng trong `account` để tự bảo đảm mỗi account phải có một profile. Điều này ảnh hưởng cả cách provider kiểm tra association lẫn thiết kế business invariant.

## 16. Không đẩy vấn đề lazy loading sang API serializer

Một endpoint trả thẳng entity:

```java
return entityManager.find(Account.class, id);
```

có thể gây các vấn đề:

- Serializer truy cập `getProfile()` và bất ngờ kích hoạt SQL.
- Nếu context đã đóng và association còn lazy, có thể xảy ra lỗi lazy initialization.
- Quan hệ hai chiều `Account.profile.account` có thể tạo vòng lặp serialization.
- API vô tình công bố trường nội bộ trong profile.
- Tải nhiều dữ liệu hơn hợp đồng trả về yêu cầu.

**DTO cho use case** thường rõ ràng hơn:

```java
public record AccountDetailResponse(
    Long id,
    String username,
    String displayName
) { }
```

Service query entity với fetch plan phù hợp hoặc dùng projection để tạo DTO trong transaction. Khi đó boundary API không phải tự quyết định lúc nào lazy association cần được tải.

Một số dự án dùng “Open Session in View” hoặc cơ chế giữ persistence context mở suốt request để cho phép lazy loading trong serializer. Cách này có thể làm request hoàn thành, nhưng **không giải quyết tự động N+1 và khiến truy vấn có thể xảy ra ngoài vị trí service mong muốn**. Nên hiểu rõ trade-off thay vì coi đó là cách sửa mọi vấn đề lazy.

## 17. So sánh các chiến lược theo use case

| Tình huống | Hướng xử lý nên cân nhắc | Lý do |
|---|---|---|
| Trang danh sách chỉ cần ID và username | DTO projection chỉ chọn cột cần dùng | Tránh hydrate profile ngoài nhu cầu |
| Trang chi tiết luôn cần profile | `LEFT JOIN FETCH` hoặc entity graph tải profile | Nhu cầu đọc rõ ràng; giảm truy vấn bất ngờ |
| Account có thể không có profile | `LEFT JOIN` khi cần account và profile | Không làm mất account thiếu profile |
| Profile có FK tới account, cần đọc account tùy lúc | `@OneToOne(fetch = LAZY)` phía owner, đo provider | FK sẵn có có thể giúp trì hoãn, nhưng không bảo đảm |
| Account inverse `mappedBy` thường gây SELECT phụ | Đo SQL; cân nhắc projection, fetch join, shared key hoặc cấu hình enhancement | Giảm truy vấn bằng chiến lược phù hợp |
| Quan hệ thực sự luôn tồn tại | Mapping `optional = false` phản ánh invariant thật | Có thể hỗ trợ tối ưu và thể hiện domain đúng |
| Đã dùng Hibernate và muốn lazy inverse | Kiểm tra version + enhancement + SQL trace | Tính năng chi tiết là provider-specific |
| Tải số lượng lớn entity cùng lúc | Phân trang; projection, fetch join một-một hoặc batch phù hợp | Tránh N+1 và tải dữ liệu không cần |
| Dữ liệu chứa biography LOB lớn | Projection metadata, tách bảng/LOB khi cần | Giảm I/O và bộ nhớ |
| Chuyển DB/provider | Đo lại trong môi trường đích | Cách join, cache và lazy khác nhau |

Không có một annotation có thể tối ưu tất cả truy vấn. Lựa chọn tốt phụ thuộc **mức độ cần dữ liệu, cấu trúc quan hệ và tải thực tế**.

## 18. Những nhầm lẫn phổ biến

### 18.1. “`@OneToOne(fetch = LAZY)` luôn bảo đảm không SELECT phụ”

**Sai.** LAZY là gợi ý. Provider có thể phải nạp sớm, đặc biệt ở phía inverse để xác định association tồn tại hay không.

### 18.2. “`@OneToOne` mặc định LAZY vì chỉ có một phần tử”

**Sai.** `@OneToOne` mặc định `FetchType.EAGER` theo JPA. `@ManyToOne` cũng thường mặc định EAGER; collection `@OneToMany` và `@ManyToMany` có mặc định LAZY.

### 18.3. “EAGER nghĩa là một query JOIN”

**Sai.** EAGER quy định yêu cầu dữ liệu được tải, còn provider có thể dùng JOIN hoặc các SELECT riêng. Vì vậy EAGER có thể vẫn gây N+1.

### 18.4. “`mappedBy` khiến bên inverse không cần kiểm tra profile”

**Sai.** `mappedBy` chỉ xác định phía sở hữu quan hệ. Với FK ở bảng đối diện, inverse side có thể chưa biết profile có tồn tại hay không và cần truy vấn.

### 18.5. “`optional = false` tự tạo hàng liên kết trong DB”

**Sai.** `optional = false` là khai báo mapping. Nó không tự tạo profile thiếu, không tự bảo đảm mọi account có profile khi FK nằm ở bảng profile.

### 18.6. “`@JoinColumn(unique = true)` đủ để bảo đảm tải lazy”

**Sai.** Unique constraint bảo vệ tính một-một ở database; nó không tự tạo proxy, bytecode enhancement hay fetch plan.

### 18.7. “Bên owning và bên inverse luôn có cùng hiệu năng”

**Sai.** Owning side thường có FK trong row đang đọc, còn inverse side có thể cần kiểm tra tồn tại và tìm ID liên kết. Tác động thực tế phải đo.

### 18.8. “Shared primary key chắc chắn loại bỏ mọi SELECT phụ”

**Sai.** Shared key giúp provider biết ID có thể có, nhưng vẫn còn câu hỏi association có thật sự tồn tại không. Sự tối ưu phụ thuộc mapping và provider.

### 18.9. “Chỉ cần bật bytecode enhancement là mọi mapping trở thành LAZY”

**Sai.** Enhancement mở ra khả năng trì hoãn ở một số trường hợp, nhưng không biến mọi mapping, mọi query hoặc mọi provider thành cùng hành vi. Cần kiểm tra version, cấu hình và SQL.

### 18.10. “`getProfile()` không phát SQL, vậy profile đã được tải sẵn”

**Sai.** Getter có thể trả proxy mà chưa lấy state. Hãy đọc một field chưa có của profile và kiểm tra SQL, đồng thời quan sát trạng thái tải.

### 18.11. “`PersistenceUnitUtil.isLoaded` đủ để đo hiệu năng”

**Sai.** Đây là API quan sát trạng thái tải theo JPA, không phải SQL profiler. Cần kết hợp log/tracing và thông tin cache/transaction.

### 18.12. “Fetch join luôn tốt hơn projection”

**Sai.** Fetch join nạp entity và state cần thiết. Nếu chỉ cần ba cột, projection có thể giảm dữ liệu và chi phí quản lý entity. Chọn theo use case.

### 18.13. “Đóng EntityManager rồi mới lấy lazy profile cũng bình thường”

**Không bảo đảm.** Với proxy/attribute chưa được khởi tạo, truy cập sau khi persistence context đóng có thể thất bại tùy provider. Dữ liệu cần trả nên được chuẩn bị khi còn ngữ cảnh thích hợp.

### 18.14. “Cache-hit chứng minh mapping không có N+1”

**Sai.** First-level/second-level cache có thể che các truy vấn. Phép đo cần nêu rõ cache state; nên kiểm chứng cả lần đọc lạnh.

### 18.15. “Không có profile thì `JOIN FETCH` và `LEFT JOIN FETCH` tương đương”

**Sai.** Inner join có thể loại account không có profile khỏi kết quả. Left join giữ lại account đó.

## 19. Quy trình đánh giá thực tế

Khi gặp một quan hệ một-một hoạt động chậm, hãy phân tích theo thứ tự:

1. **Xác định nghiệp vụ:** account có bắt buộc có profile không? Có yêu cầu luôn đọc profile không?
2. **Đọc mapping:** `@OneToOne` đặt ở đâu? Bên nào có `@JoinColumn` và bên nào có `mappedBy`?
3. **Đọc schema:** FK nằm ở bảng nào? Có unique constraint không? FK nullable không? Có shared primary key không?
4. **Kiểm tra fetch policy:** EAGER mặc định hay LAZY tường minh? Có entity graph/JOIN FETCH từ query không?
5. **Ghi rõ provider:** tên, phiên bản, dialect, enhancement/weaving và cache.
6. **Kiểm tra SQL với một entity:** số SELECT trước và sau khi truy cập association; thử cả có và không có target.
7. **Kiểm tra SQL với một danh sách:** số SELECT tăng tuyến tính theo số account hay không?
8. **Xác định nhu cầu dữ liệu:** chỉ metadata thì projection; cần entity liên kết thì fetch plan chủ động.
9. **Đo lại sau khi thay đổi:** số statement, thời gian, rows/bytes trả về và bộ nhớ.
10. **Ghi nhận kết quả theo môi trường:** tránh biến hành vi provider hiện tại thành quy tắc chung của JPA.

Một bảng ghi kết quả minh họa:

| Kịch bản | Có profile? | Mapping | Kỳ vọng cần kiểm chứng |
|---|---|---|---|
| Tải Account, không gọi getter | Có | inverse LAZY | Có SELECT tìm profile ngay không? |
| Tải Account, không gọi getter | Không | inverse LAZY | Có SELECT kiểm tra null không? |
| Tải AccountProfile, chưa đọc Account | Có | owner LAZY | FK có đủ để trì hoãn không? |
| Tải Account và gọi profile.displayName | Có | inverse LAZY | SQL xuất hiện ở bước nào? |
| Query 100 Account | Trộn | inverse EAGER | Có N+1 không? |
| Query 100 Account với `LEFT JOIN FETCH` | Trộn | fetch plan tường minh | Bao nhiêu SELECT và bao nhiêu row? |
| Query 100 Account bằng DTO | Trộn | projection | Có chỉ lấy các cột cần thiết không? |

Mục tiêu là **đưa ra quyết định từ quan sát**, thay vì gán một kết quả chắc chắn cho mọi provider.

## 20. Bài tập vận dụng

### Bài tập 1: Phân biệt chuẩn và provider

```java
@OneToOne(fetch = FetchType.LAZY)
private AccountProfile profile;
```

**Câu hỏi:** Có thể kết luận profile chắc chắn không được tải trong `entityManager.find(Account.class, id)` không?

**Gợi ý:** Không. `LAZY` là hint. Cần xem chiều liên kết, vị trí FK, provider và SQL thực tế.

### Bài tập 2: Đọc cấu trúc FK

Có:

```sql
account(id)
account_profile(id, account_id UNIQUE REFERENCES account(id))
```

`Account` có `@OneToOne(mappedBy = "account")`.

**Câu hỏi:** Vì sao tải `Account` có thể phát sinh query bổ sung ngay cả khi profile được đánh dấu LAZY?

**Gợi ý:** Row `account` không chứa `profile.id` hoặc FK tới profile. Provider có thể phải kiểm tra bảng `account_profile` để biết association có tồn tại và ID profile là gì.

### Bài tập 3: Đọc log SQL

Cho log giả định:

```sql
SELECT a.id, a.username FROM account a WHERE a.id = 42;
SELECT p.id, p.account_id, p.display_name
FROM account_profile p WHERE p.account_id = 42;
```

**Câu hỏi:** Chỉ từ log có thể kết luận đã có lazy loading không?

**Gợi ý:** Chưa. Cần biết câu SELECT thứ hai xảy ra ngay trong `find()`, khi `getProfile()` được gọi, hay khi getter của profile được truy cập. Cũng cần xét EAGER và cache.

### Bài tập 4: Chọn fetch join

Một số tài khoản chưa có profile, nhưng API cần trả danh sách **tất cả** tài khoản cùng tên hiển thị nếu có.

**Câu hỏi:** Chọn `join fetch` hay `left join fetch`?

**Gợi ý:** `left join fetch` nếu cần entity + association; hoặc dùng `LEFT JOIN` trong DTO projection nếu chỉ cần vài cột. `join fetch` dạng inner có thể loại account không có profile.

### Bài tập 5: Shared primary key

`AccountProfile.id` vừa là PK vừa là FK tới `Account.id` với `@MapsId`.

**Câu hỏi:** Có thể kết luận inverse `Account.profile` lazy được trong mọi provider không?

**Gợi ý:** Không. Shared PK cho biết ID mục tiêu có thể có nhưng không bảo đảm row profile tồn tại hoặc provider trì hoãn truy vấn kiểm tra.

### Bài tập 6: N+1 dù không đọc profile

Một API liệt kê 100 account chỉ trả username, nhưng SQL log có 101 SELECT.

**Câu hỏi:** Hai nguyên nhân liên quan `@OneToOne` cần điều tra là gì?

**Gợi ý:** (1) Association còn EAGER và provider dùng secondary SELECT; (2) phía inverse LAZY nhưng provider kiểm tra tồn tại từng profile. Cần xác nhận với mapping và trace thực tế.

### Bài tập 7: So sánh ba cách lấy dữ liệu

Trang danh sách cần `id`, `username`, `displayName`. Có ba cách:

- `findAll` các Account rồi gọi `getProfile()`.
- JPQL `LEFT JOIN FETCH` profile.
- JPQL constructor projection sang `AccountSummary`.

**Câu hỏi:** Cách nào thường rõ ý định nhất nếu client chỉ cần ba trường?

**Gợi ý:** Projection trả DTO với đúng dữ liệu cần thiết. Fetch join phù hợp khi ứng dụng thực sự cần managed entity và association; cách đầu dễ tạo N+1 nếu thiếu fetch plan phù hợp.

### Bài tập 8: Đọc `optional = false`

Bảng `account_profile` có FK `account_id NOT NULL UNIQUE`. Developer thêm `optional = false` trên `Account.profile` để mong JPA không query kiểm tra.

**Câu hỏi:** Khai báo này có chắc đúng nghiệp vụ không?

**Gợi ý:** Chưa chắc. FK chỉ bảo đảm mỗi profile có account, không bảo đảm mỗi account có profile. Nếu account có thể thiếu profile, khai báo non-optional là sai mô hình.

### Bài tập 9: Đánh giá phép đo

Phép đo không thấy SELECT cho profile khi gọi `find(Account.class, 42L)`, nhưng trước đó test đã tải profile trong cùng `EntityManager`.

**Câu hỏi:** Có thể kết luận mapping đã tối ưu lazy không?

**Gợi ý:** Không. First-level cache có thể che truy vấn. Dùng persistence context mới và nêu rõ cache state khi đo.

### Bài tập 10: Không nhầm ownership với fetch

```java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    fetch = FetchType.LAZY
)
private AccountProfile profile;
```

**Câu hỏi:** Attribute nào quyết định ownership, attribute nào quyết định nhu cầu tải, và cascade dùng để làm gì?

**Gợi ý:** `mappedBy` xác định phía inverse; `fetch` mô tả chiến lược tải; `cascade` lan truyền thao tác persistence. Chúng độc lập về mục đích.

## 21. Những điểm cần ghi nhớ

- **`@OneToOne` mặc định EAGER** trong JPA. EAGER là yêu cầu nạp dữ liệu, không phải bảo đảm dùng một SQL JOIN.
- **`FetchType.LAZY` là gợi ý.** Provider có thể tải sớm; không kết luận hiệu quả lazy chỉ từ annotation.
- **Phía owner chứa FK** thường có thông tin target ID ngay khi đọc row; phía inverse `mappedBy` có thể cần thêm SELECT để biết target có tồn tại và ID là gì.
- **Cấu trúc FK unique, shared primary key hoặc FK đảo chiều** ảnh hưởng khả năng lazy và SQL của provider, nhưng không thay đổi hợp đồng chuẩn về LAZY.
- **Hibernate/EclipseLink có cơ chế proxy, enhancement/weaving** và các tối ưu riêng. Phải xem phiên bản và cấu hình thực tế.
- **EAGER vẫn có thể gây N+1** nếu provider dùng secondary SELECT cho từng entity.
- Khi cần cả entity và association, **`LEFT JOIN FETCH` hoặc entity graph** giúp diễn đạt fetch plan theo use case; chúng không mặc nhiên tạo cùng một SQL trong mọi provider.
- Khi chỉ cần một số cột, **DTO projection** thường dễ giới hạn dữ liệu hơn việc tải đầy đủ entity graph.
- **Đo trước khi kết luận:** quan sát SQL trong persistence context mới, với cả association tồn tại/không tồn tại, và theo dõi cache, số statement, dữ liệu chuyển qua mạng và thời gian thực thi.
- **Ownership, cascade, orphan removal, fetch và transaction là những cơ chế khác nhau.** Đừng dùng một thuộc tính để suy luận hoặc thay thế chức năng của thuộc tính khác.

Khi gặp một quan hệ `@OneToOne(fetch = LAZY)`, hãy bắt đầu bằng hai câu hỏi: **khóa ngoại nằm ở phía nào, và provider đang biết được điều gì về association tại thời điểm tải entity?** Sau đó dùng SQL log trong cấu hình thật để xác nhận. Cách tiếp cận này giúp đánh giá quan hệ một-một theo cả **hợp đồng JPA** lẫn **hành vi provider**, đồng thời chọn chiến lược tải dữ liệu phù hợp cho từng thao tác.
