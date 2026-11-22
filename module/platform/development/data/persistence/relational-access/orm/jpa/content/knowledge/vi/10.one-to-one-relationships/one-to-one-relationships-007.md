# Cập nhật hoặc thay thế đối tượng liên quan đúng phía sở hữu trong quan hệ một–một JPA

Trong Jakarta Persistence (JPA), một quan hệ `@OneToOne` nối hai entity theo quy tắc: **mỗi bản ghi ở phía này liên kết với tối đa một bản ghi ở phía kia, và ngược lại**. Ví dụ một tài khoản có tối đa một hồ sơ người dùng, một hồ sơ thuộc đúng một tài khoản. Ở Java, hai entity có thể cùng giữ tham chiếu đến nhau; ở cơ sở dữ liệu quan hệ, mối liên kết thường được lưu bằng **một cột khóa ngoại (foreign key, FK) có ràng buộc duy nhất**.

Khi cập nhật hoặc thay thế đối tượng liên quan, câu hỏi quyết định là: **phía nào sở hữu quan hệ (owning side)?** Trong một quan hệ hai chiều, JPA dùng trạng thái ở owning side để đồng bộ khóa ngoại. Thay đổi riêng tham chiếu trên phía ngược (*inverse side*) có thể làm các object trong bộ nhớ trông như đã được liên kết nhưng dữ liệu SQL vẫn không đổi.

Bài học này trình bày cách nhận diện owning side, cập nhật thuộc tính của đối tượng liên quan, chuyển liên kết, thay thế một bản ghi bằng bản ghi mới và xử lý những vấn đề thường gặp với `UNIQUE`, `orphanRemoval`, `cascade`, `@MapsId`, transaction và persistence context.

## 1. Phân biệt quan hệ trong Java với liên kết trong cơ sở dữ liệu

Giả sử ứng dụng có hai entity:

- `UserAccount`: tài khoản đăng nhập.
- `UserProfile`: thông tin hồ sơ mở rộng của một tài khoản.

Trong Java, ta muốn điều hướng được cả hai chiều:

~~~text
UserAccount                               UserProfile
------------------------                  ----------------------
id = 10                                   id = 501
email = "an@example.com"                  displayName = "An"
profile ----------------------┐     ┌---- account
                              │     │
                              └─────┘
~~~

Trong database, một thiết kế phổ biến là để bảng `user_profiles` giữ FK `account_id`:

~~~text
user_accounts                          user_profiles
--------------------------             ---------------------------------------
id (PK) | email                        id (PK) | account_id (FK, UNIQUE) | name
10      | an@example.com              501     | 10                      | An
20      | binh@example.com            502     | 20                      | Binh
~~~

Tại đây:

1. `user_profiles.account_id` trỏ tới `user_accounts.id`.
2. `FOREIGN KEY` bảo đảm một profile chỉ trỏ tới account tồn tại.
3. `UNIQUE(account_id)` bảo đảm một account không bị hai profile cùng tham chiếu.
4. `NOT NULL(account_id)` bảo đảm mỗi profile có account, nếu nghiệp vụ yêu cầu.
5. Việc tồn tại FK ở bảng profile khiến **`UserProfile.account` là phía sở hữu quan hệ** trong mapping JPA tương ứng.

Điểm số 5 không phụ thuộc vào việc tài khoản có phương thức `setProfile()` hay màn hình chỉnh sửa được đặt ở lớp nào. “Owning” là thuật ngữ **sở hữu việc ánh xạ liên kết**, không có nghĩa entity đó sở hữu toàn bộ vòng đời nghiệp vụ của entity còn lại.

## 2. Nhận diện owning side bằng `@JoinColumn` và `mappedBy`

Trong quan hệ một–một hai chiều:

- Phía dùng `@JoinColumn` để mô tả FK thường là **owning side**.
- Phía dùng `@OneToOne(mappedBy = "...")` là **inverse side**.
- Giá trị của `mappedBy` là **tên field hoặc property Java ở owning side**, không phải tên cột SQL.

Ví dụ:

~~~java
// Trong UserProfile: owning side
@OneToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private UserAccount account;
~~~

~~~java
// Trong UserAccount: inverse side
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private UserProfile profile;
~~~

Sơ đồ:

~~~text
                    mappedBy = "account"
UserAccount.profile --------------------------+
        (inverse side)                       |
                                             v
                                    UserProfile.account
                                        (owning side)
                                             |
                                    @JoinColumn("account_id")
                                             |
                                             v
                                 user_profiles.account_id
                                             |
                                    FOREIGN KEY + UNIQUE
                                             |
                                             v
                                    user_accounts.id
~~~

**Một quan hệ Java hai chiều không có nghĩa database chứa hai khóa ngoại.** Trong ví dụ trên, hai field Java cùng mô tả *một* liên kết được lưu ở *một* cột FK.

Nếu một entity chỉ khai báo `@OneToOne` không có `mappedBy`, không thể tự giả định nó là phía ngược. Phải nhìn toàn bộ mapping và cách provider được cấu hình lưu liên kết. Hai phía đều tự khai báo `@JoinColumn` một cách độc lập có thể tạo ra hai mapping quan hệ khác nhau, trái với ý định một quan hệ hai chiều.

## 3. Một mô hình JPA nhất quán để thực hành

Các ví dụ bên dưới dùng **field access**, vì `@Id` và annotation ánh xạ đều đặt trên field. Mối quan hệ do `UserProfile` sở hữu, bảng profile có surrogate PK riêng. Các đoạn Java minh họa sử dụng API `jakarta.persistence`.

### 3.1. Entity `UserAccount` ở inverse side

~~~java
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
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true, length = 320)
    private String email;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private UserProfile profile;

    protected UserAccount() {
    }

    public UserAccount(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public UserProfile getProfile() {
        return profile;
    }

    // Duy trì tham chiếu Java ở phía ngược.
    // Việc ghi account_id vẫn phải thực hiện qua UserProfile.account.
    void synchronizeProfile(UserProfile profile) {
        this.profile = profile;
    }
}
~~~

Phương thức `synchronizeProfile()` có phạm vi package-private để mã nghiệp vụ cùng package đồng bộ trạng thái trong bộ nhớ. Nó **không phải thao tác thay FK**. Có thể đặt phương thức này trong một aggregate helper khác, miễn sao trách nhiệm cập nhật owning side được thực hiện nhất quán.

### 3.2. Entity `UserProfile` ở owning side

~~~java
package com.example.persistence;

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
import jakarta.persistence.Version;

@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true,
        foreignKey = @ForeignKey(name = "fk_profile_account")
    )
    private UserAccount account;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Column(name = "biography", length = 1000)
    private String biography;

    @Version
    private long version;

    protected UserProfile() {
    }

    public UserProfile(String displayName, String biography) {
        this.displayName = displayName;
        this.biography = biography;
    }

    public Long getId() {
        return id;
    }

    public UserAccount getAccount() {
        return account;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getBiography() {
        return biography;
    }

    public void updateDetails(String newName, String newBiography) {
        this.displayName = newName;
        this.biography = newBiography;
    }

    void assignTo(UserAccount account) {
        this.account = account;
    }
}
~~~

`@Version` giúp phát hiện một số xung đột cập nhật cùng profile qua cơ chế optimistic locking. Nó **không tự bảo đảm** hai transaction đồng thời thay toàn bộ profile của một account sẽ được tuần tự hóa; trường hợp đó cần xem xét thêm khóa trên account hoặc cơ chế phối hợp khác.

### 3.3. Schema SQL tương ứng

Ví dụ DDL theo cú pháp PostgreSQL:

~~~sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE user_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    biography VARCHAR(1000),
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_user_profiles_account UNIQUE (account_id),
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES user_accounts(id)
);
~~~

`unique = true` trong `@JoinColumn` là metadata của JPA; ràng buộc `UNIQUE(account_id)` **phải thực sự tồn tại tại database** để ngăn dữ liệu trùng từ mọi đường ghi, kể cả JDBC và công cụ ngoài ORM. Nếu schema được tạo bằng migration, chính migration mới xác lập ràng buộc vật lý.

## 4. Sai lầm điển hình: chỉ cập nhật phía `mappedBy`

Giả sử đang có một tài khoản chưa có profile. Đoạn mã sau thể hiện *ý định* gắn profile nhưng chỉ thay inverse side:

~~~java
UserAccount account = em.find(UserAccount.class, 10L);
UserProfile profile = new UserProfile("An", "Lập trình Java");

account.synchronizeProfile(profile); // Chỉ đổi field phía inverse.
em.persist(profile);                // Chưa thiết lập profile.account.
~~~

Vì `UserProfile.account` chưa được gán:

- Owning side chưa có giá trị FK hợp lệ để ghi.
- Với `optional = false` và `account_id NOT NULL`, provider/database có thể báo lỗi khi flush.
- Dù bỏ các ràng buộc đó, chỉ sửa `UserAccount.profile` cũng không phải là cách chuẩn để ghi liên kết.

Đoạn đúng về mặt liên kết phải thiết lập **owning side**:

~~~java
UserAccount account = em.find(UserAccount.class, 10L);
UserProfile profile = new UserProfile("An", "Lập trình Java");

profile.assignTo(account);          // OWNING SIDE: quyết định account_id.
account.synchronizeProfile(profile); // INVERSE SIDE: đồng bộ object graph.
em.persist(profile);
~~~

Khi transaction được commit, provider có thể phát INSERT vào `user_profiles` với `account_id = 10`. Vì `UserAccount` đã được tìm bằng `find`, đây là entity managed; ví dụ không cần persist lại account.

**Quy tắc:** để database lưu liên kết đúng, phải thay trạng thái của bên sở hữu. Để mã Java không nhìn thấy hai hình ảnh quan hệ mâu thuẫn trong cùng persistence context, nên cập nhật cả hai tham chiếu.

## 5. Cập nhật dữ liệu profile khác với thay thế chính profile

Cụm từ “cập nhật profile” có thể chỉ hai yêu cầu rất khác nhau:

1. **Sửa thuộc tính của cùng profile:** đổi tên hiển thị hoặc tiểu sử; profile ID và FK không thay đổi.
2. **Thay bản ghi profile bằng bản ghi khác:** xóa hoặc tách profile cũ rồi gắn profile mới; có thể tạo ID mới, thay đổi vòng đời và ảnh hưởng unique constraint.

Nếu nghiệp vụ chỉ yêu cầu đổi tên hoặc tiểu sử, phương án thứ nhất thường rõ ràng và ít tốn kém hơn:

~~~java
UserAccount account = em.find(UserAccount.class, accountId);
if (account == null) {
    throw new IllegalArgumentException("Không tìm thấy tài khoản");
}

UserProfile profile = account.getProfile();
if (profile == null) {
    throw new IllegalStateException("Tài khoản chưa có profile");
}

profile.updateDetails("Nguyễn An", "Thông tin đã cập nhật");
// Khi profile còn managed, provider theo dõi thay đổi.
// Transaction commit sẽ đồng bộ UPDATE theo quy tắc flush.
~~~

Thao tác này **không cần tạo đối tượng `UserProfile` mới, không cần gọi `merge` trên entity đang managed và không cần sửa `account_id`**. Database thường cần UPDATE các cột dữ liệu và version của hàng profile, không cần DELETE/INSERT.

### Khi nào thực sự cần thay thế entity?

Thay thế bằng một bản ghi mới có thể là yêu cầu hợp lệ khi:

- Profile cũ đã thuộc một phiên bản tài liệu cần đóng vòng đời.
- Có yêu cầu tạo mã/ID mới rõ ràng.
- Cần xóa dữ liệu cũ và xây dựng đối tượng mới với quy tắc vòng đời khác.
- Domain định nghĩa đây là hai thực thể khác nhau, không phải cùng một profile được chỉnh sửa.

Nếu các bảng khác còn tham chiếu profile cũ, xóa nó có thể bị foreign key chặn. Khi đó phải cân nhắc cập nhật tại chỗ, lưu lịch sử hoặc chuyển tham chiếu trước khi xóa. Không dùng “thay entity” như cách mặc định để cập nhật vài field.

## 6. Tạo profile lần đầu: thao tác phía sở hữu và transaction

Ví dụ service thực hiện trong một transaction có thể viết:

~~~java
public UserProfile createProfile(
        EntityManager em,
        long accountId,
        String displayName,
        String biography) {

    UserAccount account = em.find(UserAccount.class, accountId);
    if (account == null) {
        throw new IllegalArgumentException("Không tìm thấy account");
    }
    if (account.getProfile() != null) {
        throw new IllegalStateException("Account đã có profile");
    }

    UserProfile profile = new UserProfile(displayName, biography);
    profile.assignTo(account);            // Cột FK ở owning side.
    account.synchronizeProfile(profile);  // Đồng bộ inverse side.

    em.persist(profile);
    return profile;
}
~~~

Trong trường hợp này, `account.getProfile() == null` là kiểm tra nghiệp vụ hữu ích, **không phải biện pháp chống trùng tuyệt đối**. Hai request đồng thời có thể cùng thấy account chưa có profile. Ràng buộc `UNIQUE(account_id)` của database sẽ bảo vệ tính duy nhất; ứng dụng phải xử lý xung đột và rollback đúng cách.

Với chiến lược `GenerationType.IDENTITY`, provider có thể phải gửi INSERT trước commit để lấy ID. Đừng suy ra rằng `persist` luôn chờ đến commit mới phát SQL; nhưng cũng đừng coi `persist` thành công là giao dịch đã được commit.

### Một transaction Java SE tối giản

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    createProfile(em, 10L, "An", "Lập trình Java");
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

Ví dụ này dành cho `RESOURCE_LOCAL` transaction. Trong Spring hoặc Jakarta EE, transaction thường do framework/container quản lý và service được gọi trong một ranh giới transaction tương ứng.

## 7. Thay thế profile cũ bằng bản ghi mới khi FK có UNIQUE

Giả sử account 10 đang trỏ tới profile 501:

~~~text
user_profiles
id=501, account_id=10, display_name="An"
~~~

Ta muốn thay bằng profile 700:

~~~text
user_profiles
id=700, account_id=10, display_name="Nguyễn An"
~~~

Nếu đơn giản tạo profile mới rồi gọi `persist` khi profile cũ vẫn còn, database sẽ gặp hai hàng cùng `account_id = 10`. Ràng buộc `UNIQUE(account_id)` từ chối thao tác đó.

Ngay cả khi code đánh dấu profile cũ để xóa và profile mới để chèn trong cùng transaction, **không nên giả định provider luôn phát DELETE trước INSERT**. Thứ tự flush phụ thuộc provider và các thao tác đang chờ; INSERT có thể được thực thi khi hàng cũ vẫn tồn tại và gây lỗi unique constraint.

### Phương án rõ ràng: xóa cũ, flush, rồi tạo mới

Với mapping ở mục 3 **chưa khai báo `orphanRemoval` tự động**, có thể dùng một đơn vị công việc như sau:

~~~java
public UserProfile replaceProfile(
        EntityManager em,
        long accountId,
        String newDisplayName,
        String newBiography) {

    UserAccount account = em.find(UserAccount.class, accountId);
    if (account == null) {
        throw new IllegalArgumentException("Không tìm thấy account");
    }

    UserProfile oldProfile = account.getProfile();
    if (oldProfile != null) {
        em.remove(oldProfile);              // Old profile đang managed.
        account.synchronizeProfile(null);   // Đồng bộ phía inverse.
        em.flush();                         // Đưa DELETE xuống DB trước INSERT.
    }

    UserProfile replacement =
            new UserProfile(newDisplayName, newBiography);
    replacement.assignTo(account);         // Owning side có account_id.
    account.synchronizeProfile(replacement);
    em.persist(replacement);

    return replacement;
}
~~~

Mọi thao tác trên phải nằm trong **cùng một transaction**. Lệnh `flush()` đảm bảo provider đồng bộ các thay đổi đang chờ đến điểm đó, bao gồm DELETE đã được lên lịch; nó **không commit**. Nếu INSERT mới thất bại, transaction có thể rollback cả việc xóa profile cũ và việc tạo profile mới.

Trình tự ý nghĩa:

~~~text
Transaction bắt đầu
       |
       v
Tìm account, nạp oldProfile
       |
       v
em.remove(oldProfile)
account.profile = null (đồng bộ bộ nhớ)
       |
       v
em.flush() --> DELETE old profile
       |
       v
replacement.account = account (OWNING SIDE)
account.profile = replacement (INVERSE SIDE)
       |
       v
em.persist(replacement) --> INSERT khi provider cần
       |
       v
COMMIT --> hoàn tất transaction
~~~

**Điều kiện của mẫu này:**

- Profile cũ phải được phép xóa theo nghiệp vụ và không còn FK khác ngăn xóa.
- Không khai báo một cơ chế cascade hoặc orphan removal khác gây xóa trùng/hành vi khó kiểm soát trong cùng thao tác.
- Transaction bao trùm cả DELETE và INSERT; lỗi ở giữa phải dẫn đến rollback.
- Account có thể được nạp cùng với profile trong context hiện tại; ở đây `synchronizeProfile()` giữ trạng thái Java nhất quán.
- Các transaction thay profile đồng thời vẫn phải xử lý xung đột do khóa/unique constraint hoặc có cơ chế đồng bộ thích hợp.

Sau khi commit, ID profile mới **khác** ID profile cũ. Nếu API hoặc bảng khác phụ thuộc ID cũ, đây có thể là thay đổi không phù hợp; hãy xem xét sửa tại chỗ hoặc versioning.

## 8. Trường hợp owning side nằm ở `UserAccount`

Không phải mọi quan hệ một–một đều có FK ở bảng profile. Có thể thiết kế bảng `user_accounts` giữ `profile_id`:

~~~sql
CREATE TABLE user_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
);

CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    profile_id BIGINT UNIQUE,
    CONSTRAINT fk_account_profile
        FOREIGN KEY (profile_id) REFERENCES user_profiles(id)
);
~~~

Mapping tương ứng:

~~~java
// Trong UserAccount: OWNING SIDE vì bảng account giữ profile_id.
@OneToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "profile_id", unique = true)
private UserProfile profile;
~~~

~~~java
// Trong UserProfile: INVERSE SIDE.
@OneToOne(mappedBy = "profile")
private UserAccount account;
~~~

Với cách này, gọi `account.setProfile(newProfile)` hoặc sửa trực tiếp field mapped của `UserAccount` mới là thao tác quyết định cập nhật FK `user_accounts.profile_id`. Thay riêng `profile.account` ở phía `mappedBy` không phải cách ghi FK.

### Thay liên kết khác với xóa đối tượng cũ

Nếu account đang tham chiếu profile 501 và chuyển sang profile 700:

~~~text
Trước:
user_accounts.id=10, profile_id=501

Sau:
user_accounts.id=10, profile_id=700
~~~

Lúc này UPDATE tại bảng `user_accounts` có thể là đủ để đổi liên kết. **Bản ghi profile 501 không tự bị xóa** trừ khi nghiệp vụ hoặc cấu hình vòng đời yêu cầu. Nếu muốn nó bị xóa, phải có chính sách rõ về ownership vòng đời, orphanRemoval hoặc thao tác remove thích hợp.

Một chiều trong Java có thể chỉ có `UserAccount.profile`; không cần tạo field `UserProfile.account` nếu nghiệp vụ không cần điều hướng ngược. Điều quyết định vẫn là FK được lưu ở đâu.

## 9. `cascade` có thay thế việc cập nhật owning side không?

**Không.** Cascade chỉ lan truyền một số thao tác quản lý entity giữa các đối tượng liên quan. Nó không đảo ngược hướng sở hữu liên kết.

Ví dụ:

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.PERSIST)
private UserProfile profile;
~~~

Nếu gọi `em.persist(account)` và có profile mới được gắn vào account, cascade có thể giúp persist profile. Nhưng **profile.account vẫn phải trỏ đúng account** để provider có thể lưu `account_id`, vì `UserProfile` mới là owning side.

| Cơ chế | Mục đích | Điều không tự bảo đảm |
| --- | --- | --- |
| `CascadeType.PERSIST` | Lan lệnh persist | Không tự gán FK nếu owning side chưa thiết lập |
| `CascadeType.MERGE` | Lan thao tác merge | Không biến inverse side thành owner |
| `CascadeType.REMOVE` | Lan thao tác remove | Không tương đương chính sách xóa của database |
| `CascadeType.ALL` | Gộp các thao tác cascade chuẩn | Không có nghĩa mọi liên kết sẽ tự đồng bộ hai chiều |
| `orphanRemoval = true` | Xóa đối tượng con khi bị loại khỏi quan hệ sở hữu vòng đời | Không cam kết thứ tự SQL thuận lợi cho unique FK |

Đặc biệt, dùng `CascadeType.ALL` cho mọi quan hệ theo thói quen có thể khiến thao tác xóa hoặc cập nhật lan rộng ngoài ý định. Chỉ bật cascade khi **vòng đời nghiệp vụ** thật sự yêu cầu.

## 10. `orphanRemoval` khi thay một–một

Với một đối tượng con gắn chặt vào vòng đời của cha, có thể khai báo:

~~~java
// Trong UserAccount
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true)
private UserProfile profile;
~~~

Nếu profile cũ bị loại khỏi quan hệ, provider có thể đánh dấu nó để xóa theo ngữ nghĩa orphan removal. Tuy nhiên, cần nhớ:

1. **`orphanRemoval` là hành vi quản lý vòng đời entity.** Nó khác với FK `ON DELETE CASCADE` tại database.
2. **Bên sở hữu FK vẫn là `UserProfile.account`**, nên code phải đồng bộ hai phía.
3. Khi thay một profile cũ bằng profile mới có cùng `account_id`, provider có thể phải thực hiện DELETE và INSERT; **unique constraint có thể thất bại nếu INSERT xảy ra trước DELETE**.
4. Orphan removal phù hợp với đối tượng con thuộc sở hữu vòng đời của cha, không phù hợp nếu profile được chia sẻ hoặc tồn tại độc lập.

Ví dụ về thay đổi trạng thái đối tượng:

~~~java
UserProfile old = account.getProfile();
UserProfile next = new UserProfile("Tên mới", "Tiểu sử mới");

// Chỉ là mô tả ý định đổi trong object graph:
account.synchronizeProfile(next);
next.assignTo(account);
// old được loại khỏi tham chiếu của account.
~~~

Nếu mapping có orphan removal, thao tác bỏ liên kết có thể dẫn đến xóa old khi flush. **Không coi đoạn trên là phương án bảo đảm tương thích với mọi database có UNIQUE(account_id).** Cần hiểu SQL order của provider, trạng thái managed và constraint hiện có. Nếu ưu tiên tính di động và thứ tự rõ ràng, có thể chọn chiến lược xóa/flush rồi insert trong cùng transaction với mapping được thiết kế cho thao tác đó, hoặc cập nhật nội dung của profile cũ thay vì tạo hàng mới.

### Orphan removal không nhất thiết đồng nghĩa “chuyển sang parent mới”

Với child được quản lý như một thành phần sở hữu vòng đời, việc gỡ nó khỏi parent cũ rồi gắn vào parent khác là tình huống nhạy cảm. JPA quy định ý nghĩa orphan removal cho entity bị tách khỏi quan hệ; **không nên giả định có thể tái gắn một orphan sắp bị xóa cho parent khác mà mọi provider đều diễn giải như nhau**.

Nếu business yêu cầu *chuyển* profile còn nguyên danh tính sang account khác, nên mô hình hóa rõ quyền sở hữu và tránh cấu hình orphan removal tự động nếu nó xung đột với ý định chuyển.

## 11. Chuyển profile hiện có sang account khác

Giả sử profile 501 đang liên kết với account 10, sau đó nghiệp vụ yêu cầu liên kết profile này sang account 20 mà **không tạo profile mới**.

Với mapping FK ở `user_profiles.account_id`, thao tác ghi chính là thay owning side:

~~~java
UserProfile profile = em.find(UserProfile.class, 501L);
UserAccount destination = em.find(UserAccount.class, 20L);

if (profile == null || destination == null) {
    throw new IllegalArgumentException("Không tìm thấy đối tượng");
}
if (destination.getProfile() != null) {
    throw new IllegalStateException("Account đích đã có profile");
}

UserAccount previousAccount = profile.getAccount();
if (previousAccount != null) {
    previousAccount.synchronizeProfile(null);
}

profile.assignTo(destination);              // Owning side thay account_id.
destination.synchronizeProfile(profile);    // Đồng bộ inverse side.
~~~

Khi profile còn managed trong transaction, provider có thể thực hiện một câu UPDATE có ý nghĩa:

~~~sql
UPDATE user_profiles
SET account_id = 20
WHERE id = 501;
~~~

Điều cần chú ý:

- `UNIQUE(account_id)` ở database ngăn destination có hơn một profile, nhưng kiểm tra trong Java vẫn cần để cung cấp thông báo hợp lý.
- Nếu hai transaction đồng thời cùng thao tác, cần khóa hoặc chiến lược phát hiện xung đột; kiểm tra Java không đủ chống race condition.
- Nếu app không cho phép chuyển profile theo nghiệp vụ, nên từ chối operation ngay tại domain service.
- Nếu `account_id` còn là **primary key** của profile theo `@MapsId`, việc chuyển account cũng thay đổi định danh của profile, không còn là một UPDATE quan hệ đơn giản.

Một quan hệ một–một hai chiều phải được đồng bộ nhất quán trong object graph, vì phía ngược có thể đã được nạp trong persistence context. Nếu không cập nhật tham chiếu Java, `previousAccount.getProfile()` có thể tạm thời vẫn trả về profile đã chuyển cho tới khi trạng thái được refresh/clear.

## 12. Shared primary key: `@MapsId` thay đổi cách thay thế

Một thiết kế một–một khác là **profile có cùng khóa chính với account**. Lúc này cột `user_profiles.account_id` vừa là PK vừa là FK:

~~~sql
CREATE TABLE user_profiles (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    biography VARCHAR(1000),
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES user_accounts(id)
);
~~~

Mapping minh họa:

~~~java
@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    private Long accountId;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private UserAccount account;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected UserProfile() {
    }
}
~~~

Ở đây, `UserProfile.account` vẫn là owning side vì field giữ `@JoinColumn`, nhưng ID của profile **được suy ra từ ID của account liên kết**. Thao tác lưu đòi hỏi account có định danh phù hợp và profile được gán đúng account.

### Hệ quả khi cập nhật/thay thế

- **Sửa thuộc tính profile:** cập nhật cùng hàng theo PK `account_id`, thường là lựa chọn tự nhiên.
- **Tạo profile lần đầu:** cần gán `profile.account = account` trước khi persist.
- **Chuyển profile sang account khác:** sẽ đổi chính primary key, vi phạm giả định bất biến định danh của entity managed; không thực hiện như một setter thông thường.
- **Xóa rồi tạo profile mới cho cùng account:** cả hàng cũ và hàng mới có cùng PK `account_id`; cần xử lý delete và persistence context cẩn thận, vì cùng identity JPA không thể có hai managed entity độc lập đồng thời trong một context.

Với shared PK, việc tạo một object Java mới nhưng vẫn giữ cùng `account_id` **không mang lại danh tính khác cho profile**. Nếu nghiệp vụ thực chất là cập nhật hồ sơ, thay đổi trực tiếp entity managed hiện hữu thường ít bất ngờ hơn.

## 13. Hai dạng schema one-to-one và hệ quả của “thay thế”

| Thiết kế | PK profile | Cột liên kết | Phía sở hữu JPA | Thay mới cần chú ý |
| --- | --- | --- | --- | --- |
| FK ở profile, PK riêng | `user_profiles.id` | `user_profiles.account_id UNIQUE` | `UserProfile.account` | Xóa hàng cũ và xử lý UNIQUE trước khi INSERT mới |
| FK ở account, PK riêng | `user_profiles.id` | `user_accounts.profile_id UNIQUE` | `UserAccount.profile` | UPDATE FK, profile cũ vẫn tồn tại nếu không được xóa |
| Shared PK | `user_profiles.account_id` | Cùng cột vừa PK vừa FK | `UserProfile.account` với `@MapsId` | Cùng PK không thể cùng lúc có hai entity managed; sửa tại chỗ thường phù hợp |
| Liên kết qua bảng trung gian | PK riêng từng bên | Join table với FK và ràng buộc UNIQUE theo bội số | Phía khai báo `@JoinTable` | Cập nhật hàng liên kết, lưu ý uniqueness của cả hai phía |

Sơ đồ của bảng trên giúp thấy: **`@OneToOne` không tự chỉ ra cột cần UPDATE**. Phải xác định cấu trúc lưu liên kết rồi mới biết field nào đóng vai trò owning side.

## 14. Một–một qua `@JoinTable`

Đôi khi schema cũ không đặt FK trực tiếp ở cả hai bảng, mà sử dụng bảng liên kết:

~~~text
user_accounts            account_profile_links            user_profiles
id                       account_id | profile_id           id
10                       10         | 501                  501
20                       20         | 502                  502
~~~

JPA có thể dùng:

~~~java
@OneToOne(fetch = FetchType.LAZY)
@JoinTable(
    name = "account_profile_links",
    joinColumns = @JoinColumn(name = "account_id"),
    inverseJoinColumns = @JoinColumn(name = "profile_id")
)
private UserProfile profile;
~~~

Giả sử annotation này đặt trong `UserAccount`, nó là owning side. Các cột `account_id` và `profile_id` nằm trong **bảng trung gian**, không nằm trực tiếp trong bảng account hoặc profile.

Để schema đúng cardinality một–một, thường cần:

~~~sql
CREATE TABLE account_profile_links (
    account_id BIGINT NOT NULL UNIQUE,
    profile_id BIGINT NOT NULL UNIQUE,
    FOREIGN KEY (account_id) REFERENCES user_accounts(id),
    FOREIGN KEY (profile_id) REFERENCES user_profiles(id)
);
~~~

Nếu bỏ `UNIQUE(account_id)`, một account có thể có nhiều hàng liên kết; nếu bỏ `UNIQUE(profile_id)`, một profile có thể gắn với nhiều account. Sử dụng `@JoinTable` không tự miễn trừ trách nhiệm thiết kế constraint tại DB.

Khi đổi profile ở owning side, provider cập nhật **hàng liên kết** theo mapping; không nên mặc định nó luôn UPDATE FK ở bảng account hoặc profile.

## 15. `optional`, `nullable`, `unique` và phạm vi bảo đảm

Giả sử mapping sở hữu FK ở profile:

~~~java
@OneToOne(optional = false)
@JoinColumn(
    name = "account_id",
    nullable = false,
    unique = true)
private UserAccount account;
~~~

Ý nghĩa từng thành phần:

| Khai báo | Ý nghĩa ở tầng JPA/schema | Điều kiện vật lý cần có |
| --- | --- | --- |
| `optional = false` | Quan hệ ở entity này được mô tả là bắt buộc | Kết hợp kiểm tra và ràng buộc phù hợp |
| `nullable = false` | Metadata cột không được NULL khi sinh DDL | `account_id NOT NULL` tại DB |
| `unique = true` | Metadata cột phải duy nhất khi sinh DDL | `UNIQUE(account_id)` tại DB |
| `@ForeignKey(name = ...)` | Tùy chỉnh metadata FK khi sinh DDL | Constraint FOREIGN KEY thực tế |

**Điểm tinh tế:** `UserProfile.account` là quan hệ bắt buộc không có nghĩa *mọi UserAccount đều phải có UserProfile*. Ràng buộc FK ở bảng profile chỉ bảo đảm **mỗi profile thuộc một account tồn tại**; nó không tự bắt mọi account phải có hàng profile. Nếu yêu cầu tất cả tài khoản đều có profile, nghiệp vụ phải có quy trình tạo đồng thời hoặc mô hình/constraint bổ sung phù hợp.

Một–một có thể là `0..1 ↔ 1`, `0..1 ↔ 0..1` hoặc có quy định khác về tính bắt buộc. Hãy mô tả **cardinality từ cả hai phía** và kiểm tra xem schema thực sự bảo đảm những gì.

## 16. Lỗi UNIQUE khi thay đối tượng: nguyên nhân và hướng giải quyết

Một lỗi điển hình:

~~~text
Trước transaction:
user_profiles(id=501, account_id=10)

Trong transaction:
remove(profile 501)
persist(profile 700, account_id=10)

SQL thực tế nếu INSERT trước DELETE:
INSERT (... account_id=10 ...)     --> UNIQUE violation
DELETE FROM user_profiles WHERE id=501
~~~

Đây không nhất thiết là lỗi của `@OneToOne`. Nó thường là hệ quả của **ràng buộc UNIQUE hợp lệ** và **thứ tự SQL không phù hợp với ý định thay thế**.

Các hướng xử lý:

1. **Ưu tiên cập nhật tại chỗ** nếu đối tượng vẫn là cùng profile: thay đổi field của entity managed, giữ ID.
2. **Xóa rồi flush trước khi insert** trong cùng transaction khi thật sự muốn thay hàng và không bị các FK khác ngăn cản.
3. **Thiết kế quan hệ có thể đổi FK thay vì thay hàng** nếu ownership ở account và domain cho phép profile tồn tại độc lập.
4. **Dùng versioning/lịch sử** nếu cần bảo toàn profile cũ thay vì xóa vật lý.
5. **Đặt ranh giới transaction và quy tắc cạnh tranh rõ ràng** để tránh hai thao tác thay thế đồng thời.

Không nên “sửa” lỗi bằng cách bỏ UNIQUE nếu nghiệp vụ vẫn yêu cầu một–một. Bỏ constraint có thể khiến nhiều profile cùng thuộc một account dù JPA khai báo `@OneToOne`.

## 17. Transaction, `flush` và rollback khi thay thế

Sự khác nhau giữa ba thao tác:

- **`persist()`:** đưa entity mới vào phạm vi quản lý để lưu; SQL có thể được phát ngay hoặc khi flush theo provider/chiến lược sinh ID.
- **`flush()`:** đồng bộ các thay đổi đang chờ của persistence context xuống database trong transaction hiện tại.
- **`commit()`:** kết thúc transaction và xác nhận các thay đổi đã commit theo cơ chế DBMS.

Một luồng thay thế an toàn về mặt ranh giới giao dịch:

~~~text
BEGIN
  -> LOAD account and old profile
  -> REMOVE old profile
  -> FLUSH delete
  -> PERSIST new profile with owning FK set
COMMIT
~~~

Nếu INSERT mới thất bại, rollback phải đưa database về trạng thái trước transaction. **Flush không làm dữ liệu trở thành kết quả đã commit**.

Sau một lỗi persistence, không nên cố tiếp tục sử dụng cùng transaction hoặc EntityManager như thể chưa có lỗi. Trong các tình huống rollback, nên kết thúc transaction và xử lý một đơn vị công việc mới với context phù hợp.

### Tránh câu SQL UPDATE FK thành NULL khi schema không cho phép

Với FK `user_profiles.account_id NOT NULL`, nếu code làm:

~~~java
oldProfile.assignTo(null);
em.flush();
~~~

provider có thể cố UPDATE `account_id = NULL`, vi phạm NOT NULL. Điều này khác với việc **xóa** bản ghi old profile. Khi quy tắc là thay hàng, sử dụng delete rõ ràng hoặc mô hình vòng đời phù hợp; đừng mặc định có thể “tách” old profile bằng cách gán null cho FK bắt buộc rồi mới chuyển tiếp.

Trong ví dụ replace ở mục 7, code gọi `em.remove(oldProfile)` và đồng bộ inverse reference mà không cần đưa old owning FK về null.

## 18. Hai request đồng thời cập nhật hoặc thay thế profile

Giả sử cả request A và B cùng đọc account 10 chưa có profile:

~~~text
Request A                     Request B
-----------                   -----------
account.profile == null       account.profile == null
create profile A              create profile B
account_id = 10               account_id = 10
INSERT                        INSERT
             UNIQUE(account_id)
       Một thao tác phải chịu xung đột
~~~

Đây là **race condition** mà kiểm tra `if (account.getProfile() == null)` không giải quyết được. Unique constraint ở database là lớp bảo vệ cuối cùng.

Với trường hợp **hai request cùng thay** một profile hiện hữu, có thể phát sinh xung đột xóa, cập nhật version hoặc UNIQUE tùy thứ tự transaction. Một chiến lược là khóa account trước khi thay, với điều kiện mọi đường ghi tham gia cùng giao thức khóa:

~~~java
UserAccount account = em.find(
        UserAccount.class,
        accountId,
        LockModeType.PESSIMISTIC_WRITE);
~~~

Đoạn trên yêu cầu transaction và import `jakarta.persistence.LockModeType`. Provider thường yêu cầu DB lock phù hợp, chẳng hạn qua một biến thể SELECT FOR UPDATE; khả năng thực thi và nguy cơ deadlock phụ thuộc DBMS.

Một lựa chọn khác là optimistic locking với `@Version` trên **aggregate root** và cơ chế tăng version phù hợp, chẳng hạn yêu cầu `OPTIMISTIC_FORCE_INCREMENT` khi nhiều thao tác thay child cần tranh chấp trên cùng parent. Chỉ đặt `@Version` trên profile cũ **không đảm bảo bảo vệ** trường hợp hai request đồng thời tạo profile đầu tiên.

Sau khi nhận lỗi locking hoặc unique constraint, ứng dụng nên:

1. Rollback transaction lỗi.
2. Phân biệt conflict dự kiến với lỗi hạ tầng.
3. Trả trạng thái nghiệp vụ phù hợp hoặc thử lại **trong transaction mới** nếu thao tác an toàn để retry.
4. Không tự động thử lại vô hạn hoặc lặp các side effect như gửi email bên ngoài transaction.

## 19. Entity managed, detached và `merge()` khi cập nhật quan hệ

JPA phân biệt entity **new**, **managed**, **detached**, **removed**. Khi xử lý một–một:

- Entity được `em.find(...)` trả về thường là managed trong context đó.
- Entity vừa `new UserProfile(...)` là new/transient, phải được persist nếu muốn tạo hàng.
- Entity detached có thể chứa tham chiếu profile cũ hoặc trạng thái chưa đồng bộ, không nên dùng nó như bản sao luôn phản ánh database.
- Entity removed đang chờ xóa trong context; không nên tái sử dụng instance ấy như một profile mới.

### `merge()` không phải “thay thế quan hệ” tự động

Giả sử API tạo một graph detached:

~~~java
UserAccount detachedAccount = ...;
UserProfile detachedProfile = ...;
detachedAccount.synchronizeProfile(detachedProfile);
~~~

Nếu `UserProfile.account` chưa được thiết lập, gọi `em.merge(detachedAccount)` không biến inverse side thành owning side. Hơn nữa, kết quả của `merge` là một instance **managed được trả về**, không nên mặc định object detached truyền vào đã trở thành managed.

Trong các API sửa hồ sơ, cách dễ kiểm soát thường là:

1. Nhận DTO chứa các field được phép sửa.
2. Mở transaction.
3. Tìm entity managed theo ID và kiểm tra quyền truy cập.
4. Cập nhật đúng thuộc tính hoặc owning side theo quy tắc nghiệp vụ.
5. Để JPA đồng bộ thay đổi tại flush/commit.

Việc merge toàn bộ object graph từ dữ liệu đầu vào còn có nguy cơ ghi đè field không được phép sửa, nạp hoặc cascade những entity không chủ đích. Đây là lý do tốt để phân biệt **DTO nhận từ API** với **entity đang được quản lý**.

## 20. Fetch type không quyết định phía sở hữu

Mặc định của `@OneToOne` trong JPA là `FetchType.EAGER`; có thể cấu hình:

~~~java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private UserProfile profile;
~~~

`LAZY` chỉ liên quan đến kế hoạch nạp dữ liệu; nó không khiến inverse side được quyền ghi FK. Một số provider có giới hạn hoặc cần bytecode enhancement để lazy-load quan hệ one-to-one ở phía inverse. Vì vậy, `account.getProfile()` có thể kích hoạt truy vấn và behavior thực tế phụ thuộc provider.

Khi service thay profile:

- Truy cập `account.getProfile()` nên diễn ra trong transaction/persistence context đang hợp lệ.
- Không dựa vào một detached entity để biết profile mới nhất của account.
- Nếu cần tải profile cùng account, có thể dùng JPQL `LEFT JOIN FETCH` hoặc entity graph.
- Không để chiến lược fetch che khuất yêu cầu cập nhật owning side.

Ví dụ JPQL:

~~~java
UserAccount account = em.createQuery(
        "SELECT a FROM UserAccount a "
      + "LEFT JOIN FETCH a.profile "
      + "WHERE a.id = :id",
        UserAccount.class)
    .setParameter("id", accountId)
    .getSingleResult();
~~~

Truy vấn fetch chỉ giúp nạp quan hệ; thao tác thay FK vẫn được quyết định theo metadata owning side.

## 21. API thay thế profile và ý nghĩa HTTP PUT/PATCH

Trong REST API, một request `PUT /accounts/10/profile` có thể có ý nghĩa **thay toàn bộ nội dung biểu diễn của profile** mà vẫn giữ nguyên identity của resource. Điều đó không bắt buộc database phải DELETE hàng cũ và INSERT hàng mới.

Ví dụ DTO:

~~~java
public record UpdateProfileRequest(
        String displayName,
        String biography) {
}
~~~

Service có thể nạp profile managed rồi gọi:

~~~java
profile.updateDetails(
        request.displayName(),
        request.biography());
~~~

Ngược lại, một yêu cầu nghiệp vụ kiểu “đóng hồ sơ cũ và tạo hồ sơ mới có ID mới” mới thực sự đòi hỏi thay entity. **Từ “replace” ở giao thức API không tự quyết định chiến lược persistence.** Cần xác định identity và vòng đời của domain object trước khi sửa mapping.

Trong API nhiều tenant, phải kiểm tra account thuộc tenant và người gọi có quyền thay đổi. Một ID profile khó đoán hoặc unique FK không thay thế authorization.

## 22. Chuyển từ FK một–một sang shared PK hoặc ngược lại

Giả sử hệ thống đang dùng:

~~~sql
user_profiles(
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE
)
~~~

Sau này nhóm phát triển muốn chuyển thành:

~~~sql
user_profiles(
    account_id BIGINT PRIMARY KEY
)
~~~

Đây là **thay đổi mô hình định danh**, không chỉ thêm `@MapsId` vào mã Java. Cần:

1. Kiểm tra hàng hiện có, trùng FK và các ràng buộc tham chiếu tới `user_profiles.id`.
2. Xác định liệu những hệ thống khác đang dùng profile ID độc lập không.
3. Thiết kế migration PK, FK của các bảng liên quan và dữ liệu lịch sử.
4. Đồng bộ mapping JPA, API và truy vấn với schema mới.
5. Xác định lại ngữ nghĩa thay thế: với shared PK, tạo profile mới cho cùng account không sinh identity khác.

Tương tự, chuyển FK từ `user_profiles.account_id` sang `user_accounts.profile_id` sẽ **đảo owning side**. Cần migration dữ liệu liên kết, cập nhật ràng buộc và sửa toàn bộ logic cập nhật/thay thế theo phía mới.

Một bug “đổi profile mà DB không thay” sau khi migration có thể đến từ việc mã vẫn đang sửa phía inverse theo mapping cũ.

## 23. Các lỗi thường gặp khi cập nhật một–một

| Biểu hiện | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Gán `account.profile = p` nhưng FK không đổi | `UserAccount.profile` có `mappedBy`, là inverse side | Gán `p.account = account` ở owning side; đồng bộ cả hai tham chiếu |
| INSERT profile mới lỗi UNIQUE `account_id` | Profile cũ vẫn còn liên kết tại DB | Cập nhật old tại chỗ hoặc xóa/flush old rồi mới insert |
| INSERT lỗi NOT NULL `account_id` | Profile mới chưa có owning reference | Gán `profile.account` trước persist |
| Xóa old profile nhưng bị FK khác chặn | Các bảng khác còn tham chiếu profile ID | Chọn chính sách vòng đời, cập nhật liên kết hoặc không xóa |
| Đổi field ở inverse side nhưng mã Java lại thấy đúng | Object graph trong memory khác database | Tránh coi getter là bằng chứng FK đã ghi; sửa owner |
| Thay một profile gây xóa đối tượng không mong đợi | Cấu hình cascade/remove quá rộng | Chỉ cascade theo ownership vòng đời |
| Chuyển child sang parent mới nhưng bị xóa | Orphan removal trên quan hệ sở hữu vòng đời | Thiết kế rõ move vs delete; không tái gắn orphan tùy tiện |
| `em.merge(detached)` không ghi liên kết mong đợi | Detached graph hoặc owning side không nhất quán | Nạp managed entity, cập nhật owner có chủ đích |
| Hai request cùng tạo profile | Kiểm tra “chưa tồn tại” bị race | Unique constraint và chiến lược concurrency |
| `@MapsId` nhưng cố thay account cho profile managed | Thay FK đồng thời đổi primary key | Xem shared PK là định danh phụ thuộc; không sửa ID trực tiếp |
| `@OneToOne(fetch=LAZY)` vẫn tạo SELECT ngoài dự kiến | Provider có giới hạn lazy cho inverse one-to-one | Xem SQL thật, cân nhắc fetch plan/enhancement |
| `@JoinColumn(unique=true)` nhưng DB cho phép trùng | Schema vật lý chưa có UNIQUE | Migration constraint, kiểm tra dữ liệu hiện hữu |

## 24. Quy trình thực hành để cập nhật đúng phía sở hữu

Với bất kỳ quan hệ `@OneToOne` nào, hãy lần lượt xác định:

1. **Quan hệ được lưu ở đâu?** FK ở bảng A, bảng B, shared PK hay join table?
2. **Mapping nào là owning side?** Tìm `@JoinColumn`/`@JoinTable`; phía có `mappedBy` là inverse.
3. **Yêu cầu đang sửa cái gì?** Chỉ nội dung của cùng entity, thay liên kết đến entity khác, hay xóa entity cũ để tạo entity mới?
4. **Đối tượng còn managed không?** Nếu là detached, nên nạp lại hoặc sử dụng merge có kiểm soát.
5. **Cập nhật owning side trước.** Đây là nơi provider lấy thông tin FK phải ghi.
6. **Đồng bộ inverse side trong memory.** Giữ hai chiều tham chiếu nhất quán để mã nghiệp vụ không đọc nhầm.
7. **Xác định vòng đời.** Có `cascade`, `orphanRemoval` hoặc FK ngoài nào ảnh hưởng xóa/thay?
8. **Kiểm tra constraint.** UNIQUE, NOT NULL, FK có cho phép trạng thái trung gian không?
9. **Chọn trình tự SQL và transaction.** Khi thay hàng có UNIQUE, cân nhắc flush xóa trước insert trong cùng transaction.
10. **Xử lý đồng thời.** Unique constraint, optimistic/pessimistic locking và phản hồi conflict rõ ràng.

Quy trình này giúp chuyển câu hỏi mơ hồ “vì sao setter không lưu quan hệ?” thành các vấn đề cụ thể: **setter ở phía nào, DB lưu FK ở đâu và trạng thái giao dịch là gì**.

## 25. Câu hỏi và tình huống vận dụng

### Tình huống 1 — Chỉ đổi tiểu sử

Account 10 có profile 501. Người dùng chỉ sửa `biography`. Có cần xóa 501 và tạo profile khác không?

**Gợi ý:** không. Đây là cập nhật thuộc tính của cùng entity. Tìm profile managed rồi sửa field trong transaction, giữ ID và FK.

### Tình huống 2 — Chỉ gán phía `mappedBy`

Mapping `UserAccount.profile` có `mappedBy = "account"`. Ứng dụng gán profile mới vào account rồi persist profile nhưng quên thiết lập `profile.account`. Vì sao thất bại?

**Gợi ý:** owning side không chứa account để ghi FK; có thể gặp NOT NULL/FK error. Phải thiết lập profile.account và đồng bộ account.profile.

### Tình huống 3 — Thay mới gặp UNIQUE

Code gọi `em.remove(old)` rồi `em.persist(next)` trong cùng transaction. DB báo trùng `account_id`. Nguyên nhân có thể là gì?

**Gợi ý:** INSERT mới có thể được thực hiện trước DELETE cũ. Nếu domain thật sự cần hàng mới và schema cho phép xóa cũ, cân nhắc flush DELETE trước INSERT; hoặc sửa old tại chỗ nếu identity không đổi.

### Tình huống 4 — Có `orphanRemoval = true`

Người dùng muốn chuyển một profile từ account A sang B mà giữ nguyên ID. Mapping trên A có orphan removal. Có nên chỉ gỡ profile khỏi A rồi gắn B?

**Gợi ý:** không nên giả định thao tác đó di động; orphanRemoval có thể xóa entity bị gỡ. Cần xem lại ownership vòng đời và chọn mô hình cho phép chuyển rõ ràng.

### Tình huống 5 — Shared PK

`UserProfile.accountId` vừa là PK vừa là FK qua `@MapsId`. Có thể đổi `profile.account` từ account 10 sang account 20 như đổi một cột bình thường không?

**Gợi ý:** không. Giá trị FK là một phần của định danh entity. Chuyển account đồng nghĩa thay primary key, trái với giả định identity ổn định của JPA.

### Tình huống 6 — FK ở bảng Account

Schema có `user_accounts.profile_id UNIQUE`. Mapping `UserAccount.profile` có `@JoinColumn(name = "profile_id")`. Phải đổi object nào để gắn profile 700?

**Gợi ý:** account là owning side; sửa `UserAccount.profile`, đồng bộ tham chiếu ngược nếu có. Profile 501 không tự bị xóa trừ khi quy tắc vòng đời yêu cầu.

### Tình huống 7 — Hai request tạo profile đồng thời

Cả hai request đều thấy account chưa có profile và gọi persist profile mới. Một request thất bại UNIQUE. Có phải bỏ UNIQUE để giải quyết?

**Gợi ý:** không. UNIQUE là ràng buộc đúng của quan hệ một–một. Xử lý conflict và cân nhắc khóa/điều phối transaction.

### Tình huống 8 — Dữ liệu không nhất quán sau khi đổi

`profile.account` đã được chuyển từ A sang B; database UPDATE thành công, nhưng trong cùng persistence context, `A.getProfile()` vẫn trả profile cũ. Tại sao?

**Gợi ý:** JPA không tự bảo đảm mọi tham chiếu ở hai chiều object graph được đồng bộ khi chỉ sửa một field. Ứng dụng nên cập nhật cả inverse side trong bộ nhớ.

## Kết luận

**Trong quan hệ một–một hai chiều, phía sở hữu là phía quyết định cách JPA ghi liên kết**, thường được nhận diện bằng `@JoinColumn` hoặc `@JoinTable`; phía có `mappedBy` chỉ là chiều ngược của cùng quan hệ. Muốn đổi liên kết thì phải cập nhật owning side, đồng thời duy trì tham chiếu inverse trong bộ nhớ để entity graph nhất quán.

Khi thay một đối tượng liên quan, cần phân biệt **cập nhật nội dung của cùng entity** với **xóa bản ghi cũ và tạo một bản ghi mới**. Trường hợp thứ hai liên quan trực tiếp tới `UNIQUE` trên FK, thứ tự SQL, `orphanRemoval`, cascade, identity và transaction. Nếu schema dùng shared PK qua `@MapsId`, việc thay đổi quan hệ còn là vấn đề thay đổi định danh, nên thường không được xử lý như một setter thông thường.

Một thao tác one-to-one đáng tin cậy phải đồng bộ ba thứ: **đúng owning side trong JPA, đúng ràng buộc FK/UNIQUE trong database và đúng quy tắc vòng đời nghiệp vụ**.
