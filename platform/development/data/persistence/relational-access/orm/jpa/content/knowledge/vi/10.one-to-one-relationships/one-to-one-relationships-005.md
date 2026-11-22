# Xử lý quan hệ tùy chọn và entity liên quan chưa tồn tại

Trong mô hình dữ liệu JPA, quan hệ **một-một** (*one-to-one*) không nhất thiết có nghĩa rằng cả hai entity luôn phải tồn tại cùng lúc. Một tài khoản có thể được tạo trước, còn hồ sơ mở rộng chỉ được bổ sung khi người dùng điền thông tin. Một khách hàng có thể chưa có thẻ thành viên; một nhân viên có thể chưa được cấp tài khoản truy cập; một đơn hàng có thể chưa có chứng từ hoàn tiền.

Những trường hợp này dẫn đến hai câu hỏi thiết kế khác nhau:

1. **Quan hệ có được phép vắng mặt không?** Chẳng hạn `Account.profile == null` là trạng thái hợp lệ khi người dùng chưa tạo hồ sơ.
2. **Nếu có một object liên quan trong Java nhưng chưa được ghi thành hàng trong database, JPA sẽ lưu nó bằng cách nào?** Chẳng hạn `Account.profile` tham chiếu `new Profile(...)`, nhưng chưa ai gọi `persist(profile)`.

Hai câu hỏi dễ bị đánh đồng. Trong JPA, **`optional = true` nói về khả năng liên kết có giá trị `null`**, còn **cascade persist hoặc thao tác persist tường minh mới giải quyết vòng đời của entity liên quan chưa tồn tại trong database**. Chọn đúng mapping, phía sở hữu và ràng buộc SQL giúp ứng dụng duy trì dữ liệu nhất quán qua cả hai tình huống.

Bài học thuộc chương **Quan hệ một-một** của chủ đề **Data Persistence, Relational Access, ORM và JPA**, sử dụng Jakarta Persistence với package `jakarta.persistence`.

## 1. Ba trạng thái cần phân biệt ngay từ đầu

Giả sử có `CustomerAccount` và `AccountProfile`. Mỗi tài khoản có tối đa một hồ sơ, và mỗi hồ sơ được liên kết với tối đa một tài khoản.

Có ba tình huống thường gặp nhưng khác nhau về mặt kỹ thuật:

| Tình huống | Trong Java | Trong database | Ý nghĩa |
| --- | --- | --- | --- |
| **Chưa có liên kết** | `account.getProfile() == null` | FK `profile_id` là `NULL`, hoặc chưa có hàng child theo schema | Hợp lệ nếu nghiệp vụ cho phép quan hệ tùy chọn |
| **Có object mới nhưng chưa lưu** | `account.getProfile() == new AccountProfile(...)` | Chưa tồn tại hàng của profile mới | Entity liên quan đang ở trạng thái **new/transient**, phải xử lý persistence |
| **Có ID được tham chiếu nhưng hàng DB không tồn tại** | Tham chiếu/proxy hoặc FK có giá trị | FK trỏ tới ID thiếu hàng tương ứng | **Liên kết bị hỏng hoặc tham chiếu chưa được xác thực**, không tương đương `null` |

Một trường hợp thứ tư cũng quan trọng: profile đã tồn tại trong DB nhưng entity Java tương ứng là **detached** vì được lấy từ một persistence context khác. Đây không phải object new, và có cách xử lý khác với profile chưa bao giờ được lưu.

Hãy đặt một câu hỏi trước khi chọn annotation: **“Không có profile” là trạng thái nghiệp vụ hợp lệ, hay là một lỗi dữ liệu/vòng đời?”**

## 2. `@OneToOne(optional = true)` có ý nghĩa gì?

Annotation `@OneToOne` thuộc chuẩn JPA/Jakarta Persistence. Thuộc tính `optional` cho biết association có thể `null` hay không:

```java
@OneToOne(optional = true)
private AccountProfile profile;
```

`optional = true` là giá trị mặc định của thuộc tính `optional`, nên có thể viết gọn:

```java
@OneToOne
private AccountProfile profile;
```

Tuy nhiên, khi trường hợp “chưa có profile” là một phần quan trọng của nghiệp vụ, viết tường minh `optional = true` làm ý định dễ đọc hơn.

Đối chiếu:

```java
@OneToOne(optional = false)
private AccountProfile profile;
```

có nghĩa mapping khai báo quan hệ **bắt buộc**. Nó phù hợp với một mô hình mà entity tương ứng không được ở trạng thái không có profile, với điều kiện schema và lifecycle cũng áp đặt quy tắc đó.

### `optional` không phải toàn bộ quy tắc dữ liệu

| Cấu hình | Ý nghĩa |
| --- | --- |
| `@OneToOne(optional = true)` | JPA association được khai báo có thể `null` |
| `@OneToOne(optional = false)` | JPA association được khai báo là bắt buộc |
| `@JoinColumn(nullable = true)` | Metadata của cột khóa ngoại cho phép `NULL` |
| `@JoinColumn(nullable = false)` | Metadata của cột khóa ngoại không cho phép `NULL` |
| `@JoinColumn(unique = true)` | Đề xuất unique constraint trên cột khóa ngoại khi sinh schema |
| `FOREIGN KEY` trong DB | Ngăn một giá trị FK không null trỏ tới hàng không tồn tại, theo quy tắc constraint |
| `UNIQUE` trong DB | Ngăn nhiều hàng sử dụng cùng một khóa liên kết, theo quy tắc uniqueness của DB |

Metadata trong annotation nên nhất quán với schema thực tế. Một ứng dụng dùng migration riêng có thể đã có bảng từ trước; khi đó thay annotation **không tự bảo đảm** DB tự đổi `NOT NULL` hoặc tạo unique constraint.

Điểm cốt lõi: **`optional = true` không tạo entity đích, không bật cascade và không cho phép khóa ngoại trỏ đến một bản ghi không tồn tại.**

## 3. Ánh xạ một-một tùy chọn bằng khóa ngoại có thể `NULL`

Một thiết kế trực quan là lưu khóa ngoại ở bảng tài khoản:

```text
customer_accounts                       account_profiles
┌────┬──────────────┬────────────┐      ┌────┬───────────┐
│ id │ username     │ profile_id │      │ id │ full_name │
├────┼──────────────┼────────────┤      ├────┼───────────┤
│  1 │ an           │ NULL       │      │ 10 │ Nguyễn An │
│  2 │ binh         │ 10         │─────>│    │           │
└────┴──────────────┴────────────┘      └────┴───────────┘

Account #1 chưa có profile.
Account #2 đã liên kết Profile #10.
```

Schema ví dụ:

```sql
CREATE TABLE account_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL
);

CREATE TABLE customer_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    profile_id BIGINT NULL,
    CONSTRAINT uq_accounts_profile UNIQUE (profile_id),
    CONSTRAINT fk_accounts_profile
        FOREIGN KEY (profile_id) REFERENCES account_profiles(id)
);
```

Cú pháp `GENERATED BY DEFAULT AS IDENTITY` là một ví dụ SQL phụ thuộc hỗ trợ của RDBMS; với database khác có thể dùng cú pháp sinh khóa tương ứng hoặc migration cụ thể.

Trong cấu trúc này:

- `profile_id = NULL` biểu diễn tài khoản chưa liên kết profile.
- `FOREIGN KEY` bảo đảm một `profile_id` có giá trị phải trỏ đến hàng profile hợp lệ.
- `UNIQUE(profile_id)` ngăn hai tài khoản liên kết cùng một profile theo mô hình một-một.
- Profile không nhất thiết phải có tài khoản; schema trên cho phép profile tồn tại độc lập.

Nhiều RDBMS cho phép nhiều giá trị `NULL` trong một cột có unique constraint, nhưng **quy tắc `NULL` với uniqueness và cách tạo index có khác biệt theo hệ quản trị**. Khi dùng SQL Server hoặc các kiểu unique index/constraint đặc thù, cần xác minh rằng thiết kế vẫn cho phép nhiều tài khoản chưa có profile. Có thể cần **filtered unique index** hoặc cấu trúc khác phù hợp database mục tiêu.

### Mapping entity theo phía sở hữu

**`AccountProfile.java`**

```java
import jakarta.persistence.*;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected AccountProfile() {}

    public AccountProfile(String fullName) {
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("fullName");
        }
        this.fullName = fullName.trim();
    }

    public Long getId() { return id; }
    public String getFullName() { return fullName; }
}
```

**`CustomerAccount.java`**

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String username;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        unique = true
    )
    private AccountProfile profile;

    protected CustomerAccount() {}

    public CustomerAccount(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username");
        }
        this.username = username.trim();
    }

    public Long getId() { return id; }
    public String getUsername() { return username; }
    public AccountProfile getProfile() { return profile; }

    public void setProfile(AccountProfile profile) {
        this.profile = profile;
    }
}
```

Đây là **quan hệ đơn hướng**: `CustomerAccount` có field `profile`, còn `AccountProfile` không biết tài khoản nào đang tham chiếu mình. `CustomerAccount.profile` là **phía sở hữu** (*owning side*) vì nó ánh xạ trực tiếp cột `profile_id`.

`FetchType.LAZY` nói về chiến lược tải; không quyết định quan hệ có tùy chọn hay không. Trong một-một, việc thực sự tải trễ được đến đâu còn phụ thuộc provider, bytecode enhancement, proxy và phía ánh xạ.

## 4. Tạo tài khoản trước, profile sau: quan hệ `null` hợp lệ

Một luồng nghiệp vụ phổ biến:

```text
Đăng ký tài khoản
       │
       ▼
CustomerAccount(username)
       │
       ├── profile = null
       └── persist(account)
                   │
                   ▼
        customer_accounts:
        (id=1, username="an", profile_id=NULL)

Một thời gian sau: người dùng bổ sung hồ sơ
       │
       ▼
Tạo AccountProfile
       │
       ├── persist(profile)
       ├── account.setProfile(profile)
       └── commit
                   │
                   ▼
        customer_accounts.profile_id = profile.id
```

Ví dụ tạo tài khoản chưa có profile:

```java
EntityManager em = ...;
em.getTransaction().begin();

CustomerAccount account = new CustomerAccount("an");
em.persist(account);

// profile == null là hợp lệ theo mapping và schema ở ví dụ.

em.getTransaction().commit();
```

Tài khoản được lưu dù chưa có profile vì quan hệ được khai báo tùy chọn và khóa ngoại cho phép `NULL`.

Khi bổ sung profile, trong một transaction khác:

```java
em.getTransaction().begin();

CustomerAccount account =
    em.find(CustomerAccount.class, accountId);

if (account == null) {
    throw new IllegalArgumentException("Account not found");
}

AccountProfile profile = new AccountProfile("Nguyễn An");
em.persist(profile);
account.setProfile(profile);

em.getTransaction().commit();
```

Với mapping **không khai báo cascade** ở trên, code gọi `em.persist(profile)` tường minh. Cả account đã managed và profile mới trở thành managed trong transaction; khi flush/commit, provider lưu profile và cập nhật FK của account theo các ràng buộc liên quan.

**Không cần tạo một bản ghi profile rỗng** chỉ để thỏa JPA nếu nghiệp vụ thực sự cho phép chưa có hồ sơ. Việc lưu “placeholder profile” có thể khiến domain khó phân biệt hồ sơ đã được hoàn thành với hồ sơ chưa hề được tạo.

## 5. `null` khác entity mới chưa `persist()`

So sánh hai dòng:

```java
account.setProfile(null);                       // Không có liên kết.
account.setProfile(new AccountProfile("An"));    // Có liên kết tới object mới.
```

Hai trạng thái không tương đương.

Ở dòng thứ hai, `AccountProfile` có instance Java nhưng chưa có hàng tương ứng trong database. Nó thường được gọi là entity **new/transient**. Một foreign key SQL phải tham chiếu được khóa chính của hàng profile sau khi hàng đó được lưu.

Nếu mapping không có cascade, đoạn sau là sai về kỳ vọng:

```java
em.getTransaction().begin();

CustomerAccount account = new CustomerAccount("an");
account.setProfile(new AccountProfile("Nguyễn An"));

em.persist(account);
em.getTransaction().commit();
```

Ứng dụng chỉ yêu cầu `persist(account)`. Vì không có `CascadeType.PERSIST`, JPA không được yêu cầu tự động persist profile mới. Tùy provider và thời điểm flush, ứng dụng có thể nhận lỗi liên quan tới **unsaved transient instance**, `PersistenceException` hoặc vi phạm ràng buộc, thay vì có hai hàng được lưu đúng như mong đợi.

**`optional = true` chỉ cho phép `null`; nó không cho phép một quan hệ trỏ tới object new mà chưa được quản lý rồi tự lưu thay.**

### Cách xử lý A: persist rõ ràng cả hai entity

```java
em.getTransaction().begin();

AccountProfile profile = new AccountProfile("Nguyễn An");
em.persist(profile);

CustomerAccount account = new CustomerAccount("an");
account.setProfile(profile);
em.persist(account);

em.getTransaction().commit();
```

Provider biết cả hai entity cần được lưu. Cách này phù hợp khi profile và account có vòng đời độc lập hoặc service cần kiểm soát việc tạo riêng.

### Cách xử lý B: cascade persist nếu vòng đời phù hợp

Nếu nghiệp vụ coi profile mới là phần được tạo cùng account, có thể khai báo:

```java
@OneToOne(
    fetch = FetchType.LAZY,
    optional = true,
    cascade = CascadeType.PERSIST
)
@JoinColumn(name = "profile_id", nullable = true, unique = true)
private AccountProfile profile;
```

Sau đó:

```java
em.getTransaction().begin();

CustomerAccount account = new CustomerAccount("an");
account.setProfile(new AccountProfile("Nguyễn An"));

em.persist(account);  // PERSIST được cascade sang profile.

em.getTransaction().commit();
```

Khi `persist(account)` được gọi, thao tác persist được lan truyền đến profile theo `CascadeType.PERSIST`. Provider sẽ phối hợp tạo khóa và phát các câu `INSERT` phù hợp để không vi phạm foreign key trong trường hợp mapping hợp lệ.

**Cascade là quy tắc lan truyền thao tác entity**, khác với `ON DELETE CASCADE` của database. Không cần tạo bảng/cột mới chỉ để có cascade.

### Cách xử lý C: dùng managed entity nếu profile đã có trong DB

Nếu profile ID 10 đã tồn tại, có thể lấy entity managed rồi gán:

```java
AccountProfile profile = em.find(AccountProfile.class, 10L);

if (profile == null) {
    throw new IllegalArgumentException("Profile not found");
}

CustomerAccount account = em.find(CustomerAccount.class, accountId);
account.setProfile(profile);
```

Khi profile **đã tồn tại**, không gọi `persist(profile)` lại. `persist` dành cho entity new; gọi trên entity detached hoặc entity đã tồn tại ngoài persistence context có thể gây lỗi hoặc hành vi không mong muốn tùy trạng thái/cascade/provider.

## 6. Chọn cascade theo vòng đời, không theo sự tiện lợi

`CascadeType.PERSIST` giúp lưu entity mới khi lưu chủ sở hữu, nhưng cascade nào phù hợp còn phụ thuộc lifecycle.

| Cascade | Ý nghĩa chính | Khi cân nhắc |
| --- | --- | --- |
| Không khai báo cascade | Mỗi entity được persist/remove/merge bằng thao tác có chủ đích | Entity có vòng đời độc lập |
| `CascadeType.PERSIST` | Lan truyền `persist` sang entity liên quan | Hai entity thường được tạo cùng nhau |
| `CascadeType.MERGE` | Lan truyền `merge` khi đồng bộ trạng thái detached | Có use case hợp nhất graph detached rõ ràng |
| `CascadeType.REMOVE` | Lan truyền xóa sang entity liên quan | Chỉ khi quan hệ sở hữu vòng đời và không dùng chung |
| `CascadeType.ALL` | Bao gồm tất cả cascade operation chuẩn | Cần phân tích đầy đủ PERSIST/MERGE/REMOVE/... |

Với mô hình profile có thể được tạo riêng, xác thực hoặc tái sử dụng, dùng `CascadeType.ALL` chỉ để tránh gọi `em.persist(profile)` có thể gây hậu quả khi xóa account: thao tác remove có thể lan sang profile dù nghiệp vụ muốn giữ hồ sơ.

Một-một về mặt cardinality cho biết một profile chỉ liên kết tối đa một account ở thời điểm nhất định **theo constraint**, nhưng không tự nói hai entity có phải cùng vòng đời hay không. Profile vẫn có thể cần giữ lại khi account đóng hoặc chuyển sang một account khác theo quy tắc riêng.

Vì vậy, nên bắt đầu từ **không cascade** hoặc cascade đúng thao tác thực sự cần, rồi mở rộng khi có lý do nghiệp vụ.

## 7. Trường hợp profile mới được gán cho một account đang managed

Không cần phải tạo mới cả account để gặp lỗi transient association. Xét:

```java
em.getTransaction().begin();

CustomerAccount account =
    em.find(CustomerAccount.class, existingAccountId);

AccountProfile profile = new AccountProfile("Nguyễn An");
account.setProfile(profile);

// Không có persist(profile), và mapping không có cascade PERSIST.

em.getTransaction().commit();
```

Account là **managed**, provider theo dõi thay đổi `account.profile`. Nhưng profile là **new/transient**. Khi đồng bộ quan hệ, provider không có một hàng profile hợp lệ để đặt FK. Điều này có thể gây lỗi ở `flush` hoặc `commit`.

Cách khắc phục:

```java
em.getTransaction().begin();

CustomerAccount account =
    em.find(CustomerAccount.class, existingAccountId);

AccountProfile profile = new AccountProfile("Nguyễn An");
em.persist(profile);
account.setProfile(profile);

em.getTransaction().commit();
```

Nếu mapping bật cascade thích hợp và thao tác lifecycle tương ứng được thực hiện, provider có thể lan truyền thao tác theo quy tắc cascade; tuy nhiên, một giải pháp rõ ràng với entity có vòng đời độc lập là **persist trực tiếp profile mới**. Không nên giả định dirty checking của account tự thay thế việc persist entity liên quan.

## 8. Entity liên quan đã có ID nhưng hàng chưa tồn tại

Một lỗi khác là tạo một entity object và **tự gán ID** để giả vờ nó đang tồn tại trong DB:

```java
AccountProfile profile = new AccountProfile(...);
// Cố gắng gán id=999 mà không có hàng account_profiles.id=999.
account.setProfile(profile);
```

Việc một object có giá trị ID không bảo đảm hàng đã tồn tại. Tình trạng new/detached/managed được xác định bởi vòng đời persistence và bối cảnh thực tế; không thể phân loại an toàn chỉ dựa vào `id != null`.

Có thể một đoạn code sử dụng:

```java
AccountProfile profile =
    entityManager.getReference(AccountProfile.class, 999L);

account.setProfile(profile);
```

`getReference()` trả về một tham chiếu entity theo ID và có thể trì hoãn việc kiểm tra hàng thực sự tồn tại. Nếu ID 999 không có trong DB:

- Việc truy cập trạng thái của reference có thể dẫn đến `EntityNotFoundException` hoặc exception tương ứng.
- Nếu ghi FK 999 và DB có foreign key hợp lệ, lệnh SQL có thể thất bại vì **vi phạm ràng buộc tham chiếu**.
- `getReference()` không phải lệnh kiểm tra tồn tại đáng tin cậy thay cho `find()`.

Với một lựa chọn profile do người dùng cung cấp, nếu cần trả thông báo “Profile không tồn tại”, nên chủ động kiểm tra entity mục tiêu trong luồng nghiệp vụ:

```java
AccountProfile profile = em.find(AccountProfile.class, requestedProfileId);
if (profile == null) {
    throw new IllegalArgumentException("Unknown profile id");
}
```

Ngay cả sau `find()`, khi nhiều transaction cùng chạy, hàng mục tiêu vẫn có thể bị xóa hoặc thay đổi nếu không có biện pháp đồng bộ phù hợp. **Foreign key ở database là tuyến bảo vệ cuối cùng** cho toàn vẹn tham chiếu; kiểm tra ở ứng dụng không thay thế constraint.

## 9. Từ chối “liên kết mồ côi” trong database

Phân biệt rõ hai trạng thái SQL:

```text
HỢP LỆ VÌ QUAN HỆ TÙY CHỌN
customer_accounts.profile_id = NULL

KHÔNG HỢP LỆ NẾU CÓ FOREIGN KEY
customer_accounts.profile_id = 999
account_profiles không có hàng id = 999
```

`optional = true` chỉ nói trạng thái đầu có thể hợp lệ. Nó **không hợp thức hóa** trạng thái thứ hai.

Nếu tắt foreign key hoặc dữ liệu legacy đã có liên kết hỏng, provider có thể gặp lỗi khi load association. Một số provider có extension để bỏ qua reference không tồn tại, nhưng cách đó có thể che giấu dữ liệu lỗi và gắn code vào một implementation. Hướng ưu tiên thường là sửa dữ liệu, khôi phục constraint và xác định nguyên nhân tạo orphaned reference.

Ví dụ truy vấn kiểm tra liên kết hỏng:

```sql
SELECT a.id, a.profile_id
FROM customer_accounts a
LEFT JOIN account_profiles p ON p.id = a.profile_id
WHERE a.profile_id IS NOT NULL
  AND p.id IS NULL;
```

Kết quả lý tưởng là không có hàng. Nếu có, cần xử lý theo nghiệp vụ: tạo lại profile đúng, xóa liên kết, hoặc cô lập dữ liệu để điều tra. Không tự đổi tất cả liên kết hỏng thành `NULL` nếu profile có ý nghĩa nghiệp vụ quan trọng.

## 10. Phía sở hữu và phía đối ứng trong quan hệ một-một hai hướng

Nếu profile cũng cần biết tài khoản của nó, ta có thể thêm chiều ngược:

```java
// Trong CustomerAccount — owning side:
@OneToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "profile_id", nullable = true, unique = true)
private AccountProfile profile;

// Trong AccountProfile — inverse side:
@OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
private CustomerAccount account;
```

`mappedBy = "profile"` tham chiếu **tên thuộc tính Java `CustomerAccount.profile`**, không phải tên cột `profile_id`.

Với mapping này:

- `CustomerAccount.profile` là **owning side**, quản lý cột `profile_id`.
- `AccountProfile.account` là **inverse side**, phản chiếu cùng association.
- Khi đổi liên kết, phải cập nhật owning side để JPA biết foreign key cần thay đổi.
- Ứng dụng nên cập nhật cả hai tham chiếu để object graph không mâu thuẫn.

### Helper method đồng bộ quan hệ

Một cách thiết kế là chỉ cho phép thay đổi liên kết thông qua một method trên owning side. Ví dụ dưới đây bổ sung method trong hai class đã có:

**Trong `CustomerAccount`:**

```java
public void setProfile(AccountProfile newProfile) {
    if (this.profile == newProfile) return;

    if (newProfile != null &&
        newProfile.getAccount() != null &&
        newProfile.getAccount() != this) {
        throw new IllegalStateException(
            "Profile is already linked to another account"
        );
    }

    AccountProfile oldProfile = this.profile;
    this.profile = newProfile; // Phía sở hữu FK.

    if (oldProfile != null) {
        oldProfile.setAccountInternal(null);
    }
    if (newProfile != null) {
        newProfile.setAccountInternal(this);
    }
}
```

**Trong `AccountProfile`:**

```java
public CustomerAccount getAccount() {
    return account;
}

void setAccountInternal(CustomerAccount account) {
    this.account = account;
}
```

Cách này giữ hai phía nhất quán khi code ứng dụng liên kết hoặc gỡ liên kết. Method `setAccountInternal` được giới hạn trong package; ứng dụng không nên tự sửa inverse side.

Trong thực tế cần tính đến **entity detached, proxy và các object cùng đại diện một hàng nhưng không cùng tham chiếu Java** khi so sánh `==`; ví dụ trên giả định thao tác trong một object graph managed thống nhất. Nếu cần xử lý profile đã liên kết ở một persistence context khác, còn phải kiểm tra trạng thái thực tế trong database và chính sách chuyển ownership.

**Helper không thay thế database constraint.** Hai transaction khác nhau vẫn có thể đồng thời thấy profile chưa liên kết. Unique constraint, khóa và transaction sẽ quyết định kết quả cuối cùng.

## 11. Gỡ liên kết không đồng nghĩa xóa entity liên quan

Khi profile là tùy chọn, thao tác “xóa profile khỏi tài khoản” có thể mang nhiều nghĩa khác nhau.

### 11.1. Chỉ gỡ association

```java
account.setProfile(null);
```

Với mapping FK trên `CustomerAccount`, provider sẽ đồng bộ `profile_id = NULL` khi account đang managed và transaction được commit. **Hàng `account_profiles` vẫn tồn tại** nếu không có cascade remove/orphan removal hoặc thao tác xóa riêng.

SQL tương đương về ý nghĩa:

```sql
UPDATE customer_accounts
SET profile_id = NULL
WHERE id = ?;
```

Thiết kế này phù hợp nếu profile còn được lưu vì audit, cần chuyển liên kết hoặc có vòng đời độc lập.

### 11.2. Gỡ association và xóa profile cũ

Nếu profile thực sự thuộc vòng đời tài khoản và không được tái sử dụng, có thể xét:

```java
@OneToOne(
    optional = true,
    cascade = CascadeType.PERSIST,
    orphanRemoval = true
)
@JoinColumn(name = "profile_id", unique = true)
private AccountProfile profile;
```

`orphanRemoval = true` thể hiện ý định entity đích bị loại khỏi quan hệ sở hữu riêng thì được xóa khi đồng bộ theo quy tắc JPA.

Khi gọi:

```java
account.setProfile(null);
```

trên một account managed với profile hiện có, provider có thể đánh dấu profile cũ để xóa. Không nên dùng `orphanRemoval` nếu profile có thể được giữ lại hoặc chuyển sang tài khoản khác. Với một đối tượng cần tái gán, chiến lược “gỡ rồi gán” trên entity orphan có thể không có ngữ nghĩa portable và dễ dẫn tới xóa ngoài ý muốn.

### 11.3. Xóa account

Nếu chỉ dùng `CascadeType.PERSIST`, việc xóa account **không tự lan truyền thao tác REMOVE** sang profile. Cần xác định profile sẽ được giữ lại, xóa bằng service hoặc cấu hình cascade/orphan removal theo nghiệp vụ.

Không nên chọn `CascadeType.ALL` chỉ để “đỡ phải gọi persist”: nó cũng gồm xóa, merge và các thao tác lifecycle khác. Chỉ nên bật cascade khi vòng đời đúng với mô hình dữ liệu.

## 12. Thiết kế thay thế: khóa ngoại nằm ở bảng profile

Không phải quan hệ tùy chọn nào cũng nên đặt `profile_id` trong bảng account. Một thiết kế khác là để profile giữ `account_id`:

```text
customer_accounts           account_profiles
┌────┬──────────┐           ┌────┬───────────┬────────────┐
│ id │ username │           │ id │ full_name │ account_id │
├────┼──────────┤           ├────┼───────────┼────────────┤
│  1 │ an       │◄──────────│ 10 │ Nguyễn An │ 1          │
│  2 │ binh     │           └────┴───────────┴────────────┘
└────┴──────────┘

Account #2 tồn tại nhưng chưa có hàng profile.
Profile #10 thuộc Account #1.
```

Schema:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL UNIQUE,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_profiles_account
        FOREIGN KEY (account_id) REFERENCES customer_accounts(id)
);
```

Trong thiết kế này:

- Account được phép tồn tại mà **không có hàng profile**.
- Mọi profile phải tham chiếu một account tồn tại vì `account_id NOT NULL` và foreign key.
- `UNIQUE(account_id)` bảo đảm mỗi account có tối đa một profile.
- Database **không cần cột `profile_id` trong account**; sự vắng mặt của quan hệ được thể hiện bởi **không có hàng con**.

Mapping hai hướng tương ứng:

**Trong `CustomerAccount` (inverse side):**

```java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY, optional = true)
private AccountProfile profile;
```

**Trong `AccountProfile` (owning side):**

```java
@OneToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "account_id", nullable = false, unique = true)
private CustomerAccount account;
```

Ở đây hai giá trị `optional` không mâu thuẫn:

- `CustomerAccount.profile` là tùy chọn vì account có thể chưa có profile.
- `AccountProfile.account` là bắt buộc vì một profile không được tồn tại mà không có account.

**Điểm chính:** “Một-một tùy chọn” cần được xét **theo chiều nghiệp vụ**. Một phía có thể tùy chọn, trong khi phía còn lại bắt buộc.

### Khác biệt khi bổ sung profile

Vì foreign key nằm ở profile, entity mới cần tham chiếu account managed hoặc account sắp được persist:

```java
em.getTransaction().begin();

CustomerAccount account =
    em.find(CustomerAccount.class, accountId);

if (account == null) throw new IllegalArgumentException("Account missing");

AccountProfile profile = new AccountProfile("Nguyễn An");
profile.setAccount(account); // Mapping phía owning bên Profile.
em.persist(profile);

em.getTransaction().commit();
```

Method `setAccount()` cần được triển khai để gán phía sở hữu và đồng bộ inverse side khi mapping hai hướng. Không nên chỉ làm `account.profile = profile` rồi kỳ vọng foreign key `account_profiles.account_id` được ghi nếu account là inverse side.

## 13. Một-một dùng chung khóa chính: `@MapsId`

Khi profile chỉ tồn tại như phần mở rộng của account, một thiết kế phổ biến là **shared primary key**: bảng profile dùng chính khóa account làm PK và FK.

Schema:

```sql
CREATE TABLE customer_accounts (
    id BIGINT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_profiles_account
        FOREIGN KEY (id) REFERENCES customer_accounts(id)
);
```

Dữ liệu:

```text
customer_accounts.id = 1    ← có thể chưa có profile
account_profiles.id  = 1    ← khi profile được tạo

customer_accounts.id = 2    ← có thể không có hàng profile.id = 2
```

Một profile không thể tồn tại nếu không có account tương ứng do FK trên chính PK của profile. Nhưng **account vẫn có thể tồn tại mà chưa có profile**.

Mapping:

**`CustomerAccount.java` — phía đối ứng:**

```java
@Entity
@Table(name = "customer_accounts")
public class CustomerAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private AccountProfile profile;

    protected CustomerAccount() {}

    public CustomerAccount(String username) {
        this.username = username;
    }

    public Long getId() { return id; }
    public AccountProfile getProfile() { return profile; }

    void setProfileInternal(AccountProfile profile) {
        this.profile = profile;
    }
}
```

**`AccountProfile.java` — phía sở hữu:**

```java
@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    private Long id;

    @MapsId
    @OneToOne(optional = false, fetch = FetchType.LAZY)
    @JoinColumn(name = "id", nullable = false)
    private CustomerAccount account;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected AccountProfile() {}

    public AccountProfile(CustomerAccount account, String fullName) {
        if (account == null) {
            throw new IllegalArgumentException("account");
        }
        if (fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("fullName");
        }
        this.account = account;
        this.fullName = fullName.trim();
        account.setProfileInternal(this);
    }
}
```

`@MapsId` cho biết identity của profile được suy từ entity `account`. Không gắn `@GeneratedValue` cho `AccountProfile.id` trong mô hình này: profile dùng chung ID với account.

### Quy trình tạo profile sau khi account đã tồn tại

```java
em.getTransaction().begin();

CustomerAccount account =
    em.find(CustomerAccount.class, accountId);

if (account == null) {
    throw new IllegalArgumentException("Account not found");
}
if (account.getProfile() != null) {
    throw new IllegalStateException("Account already has a profile");
}

AccountProfile profile = new AccountProfile(account, "Nguyễn An");
em.persist(profile);

em.getTransaction().commit();
```

Vì account đã managed và tồn tại trong DB, profile mới dùng identity của account và được persist tường minh. Provider phối hợp SQL `INSERT` cho bảng profile với giá trị `id` tương ứng.

Nếu cả account và profile đều được tạo trong cùng transaction, cần bảo đảm account được persist và identity của account được quản lý đúng trước/đồng thời theo quy tắc `@MapsId` và cascade đã chọn.

### Giới hạn của thiết kế shared PK

Với shared PK, profile có identity gắn chặt vào account. Di chuyển profile sang một account khác không đơn giản là sửa foreign key vì foreign key cũng là **primary key**, mà thay đổi primary key của entity managed không phải thao tác thông thường được JPA hỗ trợ. Nếu nghiệp vụ yêu cầu profile có identity độc lập hoặc có thể chuyển chủ, cần cân nhắc schema khác.

Đây là ví dụ cho thấy **đặt foreign key ở đâu là quyết định về vòng đời và identity**, không chỉ về việc chọn `optional = true`.

## 14. So sánh ba lựa chọn schema cho quan hệ tùy chọn

| Thiết kế | Cách biểu diễn account chưa có profile | Có thể có profile chưa liên kết? | Nơi sở hữu FK | Phù hợp khi |
| --- | --- | --- | --- | --- |
| FK trong `customer_accounts.profile_id` (nullable, unique) | `profile_id = NULL` | Có, nếu không thêm ràng buộc khác | Account | Account tham chiếu profile có identity/vòng đời riêng |
| FK trong `account_profiles.account_id` (NOT NULL, unique) | Không có hàng profile cho account | Không, nếu FK + NOT NULL được áp dụng | Profile | Profile là phần mở rộng có thể thêm sau nhưng không đứng độc lập |
| Shared PK: `account_profiles.id` vừa PK vừa FK | Không có hàng profile cho account | Không | Profile với `@MapsId` | Profile phụ thuộc chặt vào identity của account |

Không có schema “đúng nhất” cho mọi hệ thống. Hãy chọn theo câu hỏi nghiệp vụ:

- Profile có được tạo trước account không?
- Profile có được lưu lại sau khi account bị xóa không?
- Profile có cần identity riêng không?
- Có yêu cầu chuyển profile giữa các account không?
- Có cần truy vấn account không profile thường xuyên không?
- Hai entity có cùng vòng đời hay chỉ liên kết tạm thời?

### Một bảng không có profile không đồng nghĩa thiếu dữ liệu

Nếu mô hình cho phép tạo profile sau, việc không có hàng profile tại thời điểm tạo account là **trạng thái dự kiến**. Không nên tạo thêm hàng giả hoặc cố sửa dữ liệu cho đủ một-một nếu domain không yêu cầu.

Ngược lại, nếu tài khoản phải có hồ sơ ngay từ đầu, hãy thể hiện điều đó trong quy tắc nghiệp vụ và schema phù hợp, thay vì chỉ đặt `optional = false` mà vẫn cho phép request bỏ profile.

## 15. Thay đổi optional thành mandatory là migration

Giả sử phiên bản đầu cho phép tài khoản chưa có profile:

```java
@OneToOne(optional = true)
@JoinColumn(name = "profile_id", nullable = true, unique = true)
private AccountProfile profile;
```

Sau đó nghiệp vụ yêu cầu mọi account phải có profile:

```java
@OneToOne(optional = false)
@JoinColumn(name = "profile_id", nullable = false, unique = true)
private AccountProfile profile;
```

Đây là thay đổi hợp đồng dữ liệu, không chỉ thay annotation.

Nếu DB đã có:

| id | profile_id |
| ---: | ---: |
| 1 | NULL |
| 2 | 10 |
| 3 | NULL |

thì việc thêm `NOT NULL` sẽ thất bại hoặc buộc xử lý các hàng đang thiếu profile. Cần xác định:

1. **Các account cũ chưa có profile phải được xử lý ra sao?** Tạo hồ sơ thật, từ chối một số luồng nghiệp vụ, hay giữ trạng thái chuyển tiếp?
2. **Có thể xác định thông tin profile đúng cho các hàng cũ không?** Không nên tạo dữ liệu giả chỉ để vượt constraint nếu nó làm sai nghiệp vụ.
3. **Có còn ứng dụng phiên bản cũ tạo account không có profile?** Nếu có, bật `NOT NULL` ngay sẽ gây lỗi ghi khi rolling deployment.
4. **Schema nào phản ánh mô hình mới tốt hơn?** Có thể phải đổi hướng FK hoặc tạo bảng phụ thuộc.
5. **Ràng buộc nào bảo đảm mandatory ở cấp DB?** Một foreign key `NOT NULL` ở đúng bảng là cách đơn giản cho một số schema, nhưng shared PK với profile ở bảng con chỉ bảo đảm “profile có account”, **không tự bảo đảm mọi account đều có profile**.

Điểm cuối rất quan trọng: trong schema `account_profiles.id REFERENCES accounts.id`, việc một hàng account **không có** hàng profile không vi phạm foreign key. Nếu cần bảo đảm mọi account đều có profile ở DB, phải thiết kế constraint/quy trình thích hợp với mô hình và hệ quản trị; không thể chỉ dựa vào FK từ bảng con tới bảng cha.

## 16. Khác biệt giữa `optional`, `nullable` và `@NotNull`

Ba khái niệm thường cùng xuất hiện nhưng không đồng nghĩa:

```java
@OneToOne(optional = false)
@JoinColumn(nullable = false)
private AccountProfile profile;
```

`optional = false` là thông tin ở tầng mapping quan hệ. `nullable = false` là metadata của join column, ảnh hưởng schema generation và ý định nullability của cột.

Nếu dùng Jakarta Bean Validation:

```java
@jakarta.validation.constraints.NotNull
@OneToOne(optional = false)
@JoinColumn(nullable = false)
private AccountProfile profile;
```

`@NotNull` là ràng buộc Bean Validation có thể được framework/provider tích hợp tại những thời điểm validation phù hợp. Nó không thay thế hoàn toàn foreign key, và bản thân annotation không tự tạo hàng profile.

Một nguyên tắc thiết kế:

- Nếu **quan hệ tùy chọn**, tránh đặt `@NotNull` hoặc `nullable = false` vô tình phủ nhận trạng thái `null` hợp lệ.
- Nếu **quan hệ bắt buộc**, đảm bảo code nghiệp vụ, Bean Validation nếu dùng, mapping JPA và constraint SQL cùng hướng.
- Với **schema tồn tại sẵn**, luôn kiểm tra constraint thực tế; metadata annotation không bảo đảm đã chạy migration.

## 17. Tải quan hệ tùy chọn: `null`, proxy và query

Một-một có fetch type mặc định là `EAGER` theo JPA truyền thống. Có thể khai báo `LAZY` để yêu cầu provider trì hoãn việc tải:

```java
@OneToOne(fetch = FetchType.LAZY, optional = true)
private AccountProfile profile;
```

Tuy nhiên, một-một tùy chọn có đặc điểm riêng: provider có thể cần biết **có entity đích hay không** trước khi quyết định trả về `null` hay một tham chiếu/proxy.

### Khi FK nằm ở phía sở hữu

Nếu `CustomerAccount.profile_id` là `NULL`, provider có thể nhận biết ngay account chưa có profile từ hàng account. Nếu FK có giá trị, provider có thể trả proxy hoặc tải entity đích theo chiến lược phù hợp.

### Khi quan hệ là phía đối ứng

Với:

```java
@OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
private AccountProfile profile;
```

ở `CustomerAccount`, database có thể không có cột nào trong hàng account cho biết profile tồn tại. Provider có thể phải truy vấn bảng profile để xác định có hàng tương ứng hay không; việc lazy load trên inverse side có thể phụ thuộc bytecode enhancement và hành vi provider.

Vì vậy:

- `LAZY` không bảo đảm “không có truy vấn bổ sung” trong mọi cấu hình.
- `optional = true` không bảo đảm provider luôn trả `null` mà không kiểm tra DB.
- Truy cập một association lazy sau khi persistence context đóng có thể gây lỗi nếu chưa được tải.
- Muốn biết hiệu năng, cần xem SQL thực tế của truy vấn trên provider/database đang dùng.

### Truy vấn các account chưa có profile

Khi association được ánh xạ, JPQL có thể diễn đạt điều kiện:

```java
List<CustomerAccount> incomplete = em.createQuery(
    "SELECT a FROM CustomerAccount a " +
    "WHERE a.profile IS NULL",
    CustomerAccount.class
).getResultList();
```

Đây là truy vấn theo thuộc tính JPA; provider chuyển sang SQL tương ứng dựa trên mapping. Nếu FK ở account, điều kiện có thể đơn giản như `profile_id IS NULL`; nếu FK ở bảng profile, có thể cần phép join/exists hoặc hình thức tương đương.

Lưu ý `a.profile IS NULL` có nghĩa **không có association**, khác với một entity tham chiếu ID bị hỏng do DB không có foreign key.

### Khi cần cả account có và không có profile

Nếu viết JPQL:

```java
SELECT a FROM CustomerAccount a JOIN FETCH a.profile
```

thì `JOIN FETCH` là inner join, có thể **loại các account chưa có profile** khỏi kết quả. Với relation tùy chọn, dùng:

```java
List<CustomerAccount> accounts = em.createQuery(
    "SELECT a FROM CustomerAccount a " +
    "LEFT JOIN FETCH a.profile",
    CustomerAccount.class
).getResultList();
```

`LEFT JOIN FETCH` giữ cả các account không có profile, đồng thời yêu cầu tải profile khi tồn tại. Với trang danh sách chỉ cần username và trạng thái “đã có profile hay chưa”, có thể dùng DTO projection/aggregate phù hợp để tránh tải toàn bộ graph nếu không cần.

## 18. Transaction và thứ tự lưu khi liên kết entity mới

Nếu FK nằm ở account, phải có profile hợp lệ trước khi một câu SQL ghi `profile_id` tham chiếu đến nó được thực hiện. Điều đó không bắt buộc ứng dụng phải tự gọi `flush()` giữa mỗi lệnh `persist()`.

Ví dụ:

```java
em.getTransaction().begin();

AccountProfile profile = new AccountProfile("Nguyễn An");
CustomerAccount account = new CustomerAccount("an");

em.persist(profile);
account.setProfile(profile);
em.persist(account);

em.getTransaction().commit();
```

Provider có trách nhiệm đồng bộ các entity managed theo quy tắc JPA và ràng buộc database trong phạm vi transaction. Nó có thể quyết định thứ tự `INSERT`/`UPDATE`, tạo khóa, batching tùy strategy. Với IDENTITY, provider có thể cần lấy generated ID của profile trước khi account tham chiếu khóa đó.

Không nên thiết kế application dựa trên giả định “một `persist()` luôn lập tức phát đúng một câu `INSERT`”. JPA phân biệt:

- `persist()`: chuyển entity new vào trạng thái managed.
- `flush()`: đồng bộ thay đổi pending với database.
- `commit()`: hoàn tất transaction, nếu thành công dữ liệu được xác nhận.
- `rollback()`: hủy thay đổi transaction theo ngữ nghĩa DB.

Nếu transaction thất bại vì constraint, cần rollback và xử lý lỗi. Một persistence context sau lỗi nghiêm trọng không nên tiếp tục dùng như thể mọi trạng thái vẫn nhất quán.

## 19. Đồng thời tạo liên kết và giới hạn một-một

Giả sử hai tài khoản cùng cố liên kết tới một profile duy nhất:

```text
Transaction T1                     Transaction T2
account A.profile = P              account B.profile = P
               │                          │
               └── cạnh tranh cùng Profile P ─┘
```

Ngay cả nếu cả hai transaction trước đó kiểm tra “P chưa được liên kết”, kết quả có thể thay đổi trước khi commit. Không thể bảo đảm một-một chỉ bằng:

```java
if (profile.getAccount() == null) {
    account.setProfile(profile);
}
```

Khi hai transaction cùng chạy, cả hai có thể đọc trạng thái cũ. **Unique constraint thực sự trong database** là cơ chế quyết định cuối cùng rằng mỗi profile không được tham chiếu nhiều lần trong schema FK ở account.

Để quản lý lỗi đẹp hơn, có thể kết hợp:

- Kiểm tra điều kiện nghiệp vụ trước khi liên kết để trả thông báo sớm.
- Unique constraint/foreign key ở DB để bảo vệ race condition.
- `@Version` và optimistic locking cho entity có thay đổi liên quan phù hợp.
- Transaction boundary rõ ràng, và xử lý exception constraint thành thông báo nghiệp vụ thích hợp.
- Pessimistic lock trong những use case cần serialize thao tác theo thiết kế.

**`@Version` trên account không tự bảo đảm hai account khác nhau không dùng chung một profile**. Unique constraint vẫn cần thiết khi đó là invariant của bảng quan hệ.

## 20. Profile đã tồn tại nhưng ở trạng thái detached

Giả sử profile được lấy từ `EntityManager` khác:

```java
AccountProfile detachedProfile = em1.find(AccountProfile.class, 10L);
em1.close();

// Một lúc sau, transaction khác:
CustomerAccount account = em2.find(CustomerAccount.class, accountId);
account.setProfile(detachedProfile);
```

`detachedProfile` có thể có ID hợp lệ và hàng DB tương ứng, nhưng không được quản lý trong `em2`. Cách xử lý phụ thuộc thao tác thực tế:

- Nếu chỉ cần liên kết tới profile **đã tồn tại** và không cần cập nhật state của detached object, tìm lại profile managed bằng `em2.find(AccountProfile.class, detachedProfile.getId())` hoặc dùng reference khi đã kiểm soát tính tồn tại.
- Nếu cần hợp nhất thay đổi trên profile detached, `merge` có ngữ nghĩa riêng và trả về **managed copy**; cần hiểu cascade và xung đột dữ liệu.
- Không dùng `persist(detachedProfile)` để “đảm bảo tồn tại” — đây không phải thao tác đúng cho entity detached.

Cách đơn giản, rõ ràng:

```java
AccountProfile managedProfile =
    em2.find(AccountProfile.class, detachedProfile.getId());

if (managedProfile == null) {
    throw new IllegalArgumentException("Profile no longer exists");
}

account.setProfile(managedProfile);
```

Phân biệt **entity mới chưa có hàng**, **entity có hàng nhưng detached** và **entity tham chiếu ID không tồn tại** giúp chọn đúng `persist`, `merge`, `find` và cách xử lý lỗi.

## 21. API tạo liên kết: “không gửi”, “gửi null” và “gửi ID” là ba ý nghĩa

Ở tầng REST/API, yêu cầu thay đổi account có thể chứa:

```json
{ "username": "an" }
```

hoặc:

```json
{ "profileId": null }
```

hoặc:

```json
{ "profileId": 10 }
```

Nên quy định rõ:

| Dạng request | Ý nghĩa có thể chọn |
| --- | --- |
| Không có field `profileId` | Giữ nguyên liên kết hiện tại |
| Có `"profileId": null` | Gỡ liên kết nếu nghiệp vụ cho phép |
| Có `"profileId": 10` | Liên kết tới profile đã tồn tại có ID 10 |
| Có object profile mới | Tạo profile và liên kết trong transaction theo use case |

Với endpoint PATCH, phân biệt **field không xuất hiện** và **field xuất hiện nhưng null** là đặc biệt quan trọng. Một DTO chỉ có field `Long profileId` có thể không biểu diễn đủ hai trạng thái trên nếu serializer tự gán `null` cho cả hai. Có thể cần DTO/patch representation giữ được thông tin field có được cung cấp hay không.

API cũng cần kiểm tra:

- Người gọi có quyền liên kết tới profile đó không?
- Profile có thuộc người dùng/tổ chức phù hợp không?
- Profile có đang liên kết với account khác không?
- Endpoint gỡ liên kết có hợp lệ trong trạng thái tài khoản hiện tại không?
- Khi tạo profile mới, service có thể persist nó và account trong một transaction không?

**Nullability của JPA không thay thế validation và phân quyền nghiệp vụ.** Relation có thể `optional = true` mà vẫn có những thời điểm nghiệp vụ tạm thời không cho phép gỡ liên kết.

## 22. Lỗi thường gặp và cách nhận diện

### 22.1. `TransientPropertyValueException` hoặc lỗi unsaved transient instance

Ngữ cảnh: account trỏ tới `new AccountProfile(...)` chưa persist, không có cascade phù hợp.

```java
CustomerAccount account = new CustomerAccount("an");
account.setProfile(new AccountProfile("Nguyễn An"));
em.persist(account); // Mapping không cascade.
```

Thông báo cụ thể phụ thuộc provider; Hibernate có các lỗi về transient property value, trong khi provider khác có thể bọc trong `PersistenceException` hoặc phản ánh qua constraint tại flush.

**Hướng xử lý:** persist profile riêng hoặc dùng `CascadeType.PERSIST` khi vòng đời cho phép.

### 22.2. Vi phạm `NOT NULL`

Ngữ cảnh: code đặt profile `null` nhưng database bắt buộc `profile_id NOT NULL`.

```java
account.setProfile(null);
```

**Hướng xử lý:** quyết định lại nghiệp vụ và đồng bộ `optional`/`nullable`/schema. Nếu quan hệ bắt buộc, không cho phép chuyển sang `null`; nếu tùy chọn, migration schema phải phản ánh điều đó.

### 22.3. Vi phạm `UNIQUE`

Ngữ cảnh: hai account được liên kết tới cùng một profile dù mô hình là một-một.

**Hướng xử lý:** xác minh unique constraint và sửa workflow chuyển liên kết. Không xóa unique constraint chỉ để cho phép liên kết nhiều account: khi đó mô hình thực tế đã thành nhiều-một.

### 22.4. Vi phạm `FOREIGN KEY`

Ngữ cảnh: `profile_id` trỏ tới ID không tồn tại.

**Hướng xử lý:** bảo đảm target được persist trước khi FK được ghi, hoặc dùng `find` để xác thực profile tồn tại; kiểm tra dữ liệu bị xóa hoặc race condition.

### 22.5. `EntityNotFoundException` khi dereference proxy

Ngữ cảnh: `getReference()` tạo tham chiếu tới ID không tồn tại, hoặc DB chứa liên kết hỏng.

**Hướng xử lý:** không xem proxy là bằng chứng tồn tại; kiểm tra bằng `find` khi nghiệp vụ yêu cầu và bảo vệ bằng foreign key.

### 22.6. Cập nhật inverse side nhưng DB không đổi

Ngữ cảnh: FK nằm ở profile, còn account có:

```java
@OneToOne(mappedBy = "account")
private AccountProfile profile;
```

Ứng dụng chỉ gán `account.profile = newProfile` mà không cập nhật `newProfile.account`.

**Hướng xử lý:** cập nhật owning side cùng object graph bằng helper; `mappedBy` không sở hữu FK.

### 22.7. `CascadeType.ALL` xóa dữ liệu ngoài ý muốn

Ngữ cảnh: xóa account và cascade remove sang một profile phải được lưu giữ hoặc tái sử dụng.

**Hướng xử lý:** chọn cascade cụ thể; tách thao tác gỡ liên kết và thao tác xóa entity liên quan.

### 22.8. One-to-one `LAZY` vẫn phát sinh truy vấn

Ngữ cảnh: inverse side cần xác định có profile hay không.

**Hướng xử lý:** hiểu schema/chiều FK, xem SQL thực tế và chọn fetch plan theo use case; không coi `LAZY` là cam kết không có truy vấn.

## 23. Bài tập tình huống

### Bài tập 1: Account chưa tạo profile

Entity:

```java
@OneToOne(optional = true)
@JoinColumn(name = "profile_id", nullable = true, unique = true)
private AccountProfile profile;
```

**Câu hỏi:** Có thể `em.persist(account)` với `profile = null` không?

**Đáp án:** Có, nếu các field khác hợp lệ và schema thực tế cho phép FK `NULL`. Đây là quan hệ tùy chọn đúng nghĩa, không cần tạo bản ghi profile placeholder.

### Bài tập 2: Account trỏ đến profile new

```java
AccountProfile profile = new AccountProfile("An");
CustomerAccount account = new CustomerAccount("an");

account.setProfile(profile);
em.persist(account);
```

Mapping không có cascade.

**Câu hỏi:** Vì sao code có thể lỗi ở flush/commit?

**Đáp án:** Profile chỉ là transient object, chưa được yêu cầu persist. `optional = true` không tự persist nó. Cần `em.persist(profile)` hoặc cascade persist khi phù hợp.

### Bài tập 3: Account có FK tới ID không tồn tại

```text
customer_accounts:
id=1, profile_id=999

account_profiles:
không có id=999
```

**Câu hỏi:** Có thể nói đây chỉ là account chưa có profile nên hợp lệ nhờ `optional = true` không?

**Đáp án:** Không. `profile_id = 999` là liên kết có giá trị nhưng target không tồn tại. Nếu foreign key được áp dụng, DB phải từ chối trạng thái này. Trạng thái tùy chọn hợp lệ là FK `NULL` hoặc không có hàng con, tùy schema.

### Bài tập 4: Khóa ngoại ở bảng profile

Schema:

```text
account_profiles.account_id NOT NULL UNIQUE REFERENCES customer_accounts.id
```

Một account mới được tạo chưa có profile.

**Câu hỏi:** Quan hệ có thể tùy chọn đối với account không?

**Đáp án:** Có. Bảng profile không có hàng liên kết tới account đó. Nhưng khi profile tồn tại, `account_id` của nó phải trỏ tới một account hợp lệ. Một bên tùy chọn, bên còn lại bắt buộc.

### Bài tập 5: Shared primary key

`AccountProfile.id` vừa là PK vừa là FK đến `CustomerAccount.id` với `@MapsId`.

**Câu hỏi:** Có thể tạo account trước và profile sau không? Profile có thể được chuyển sang account khác chỉ bằng setter ID không?

**Đáp án:** Có thể tạo account trước rồi thêm hàng profile dùng cùng ID. Không nên chuyển profile bằng cách sửa primary key của managed entity; nếu cần khả năng chuyển chủ, nên thiết kế identity và schema khác.

### Bài tập 6: Đổi optional thành mandatory

Hiện có nhiều account `profile_id = NULL`. Nhóm phát triển đổi `@OneToOne(optional = false)` nhưng chưa migration DB.

**Câu hỏi:** Đã bảo đảm mọi account có profile chưa?

**Đáp án:** Chưa. Metadata JPA không tự sửa dữ liệu cũ và không bảo đảm migration constraint. Cần xử lý các account thiếu profile, cập nhật code luồng tạo mới, schema và thứ tự triển khai.

### Bài tập 7: Truy vấn mất account thiếu profile

JPQL:

```java
SELECT a FROM CustomerAccount a JOIN FETCH a.profile
```

**Câu hỏi:** Vì sao trang danh sách có thể không hiển thị account chưa có profile?

**Đáp án:** Inner join loại bản ghi không có đối tượng liên kết. Dùng `LEFT JOIN FETCH` khi muốn giữ các account không có profile.

### Bài tập 8: Hai transaction cùng gán một profile

Cả hai transaction cùng kiểm tra profile chưa liên kết, rồi mỗi transaction gán profile cho một account khác nhau.

**Câu hỏi:** Validation Java đã đủ để giữ quan hệ một-một chưa?

**Đáp án:** Chưa. Phải có unique constraint thực tế trong DB, kết hợp transaction/locking và xử lý lỗi cạnh tranh.

## 24. Quy trình thiết kế quan hệ một-một tùy chọn

Khi mô hình hóa một association có thể chưa tồn tại, hãy tự trả lời những câu hỏi:

1. **“Chưa có” nghĩa là gì trong domain?** Không có liên kết `null`, chưa có hàng child, hay có object mới cần lưu?
2. **Entity nào có thể tồn tại độc lập?** Nếu profile phụ thuộc account, FK ở profile hoặc shared PK có thể phù hợp.
3. **Khóa ngoại nằm ở đâu?** Xác định owning side và cột SQL cụ thể.
4. **Trạng thái thiếu liên kết có được DB cho phép không?** Chọn `NULL` hoặc không có hàng dependent, không tạo FK hỏng.
5. **Một-một được bảo vệ ở DB thế nào?** Kiểm tra `UNIQUE`, PK/FK, và quy tắc nhiều `NULL` của RDBMS.
6. **Khi tạo entity liên quan mới, ai persist nó?** Service gọi `persist` riêng hay mapping bật `CascadeType.PERSIST` có chủ đích?
7. **Khi gỡ liên kết, có xóa target không?** Chọn giữa đặt `null`, xóa hàng, orphan removal hoặc chuyển chủ theo nghiệp vụ.
8. **Nếu hai hướng, ai là owner và ai dùng `mappedBy`?** Helper phải đồng bộ cả reference trong bộ nhớ và phía sở hữu FK.
9. **Có thể có transaction cạnh tranh không?** Đặt constraint và cách xử lý optimistic/pessimistic locking phù hợp.
10. **Query cần cả entity có/không có liên kết không?** Dùng `LEFT JOIN` khi cần giữ phía không có target; cân nhắc fetch plan và DTO.
11. **Entity đã có ID thuộc trạng thái nào?** Tránh đánh đồng transient, managed, detached và proxy tới ID không tồn tại.
12. **Nếu đổi optionality về sau, migration sẽ xử lý dữ liệu cũ thế nào?** Bảo đảm phiên bản cũ/mới không ghi dữ liệu trái ràng buộc khi triển khai.

Quy trình này giúp đưa việc chọn annotation vào đúng bối cảnh nghiệp vụ, thay vì sửa `optional` hoặc cascade dựa trên một lỗi runtime đơn lẻ.

## Kết luận

Trong quan hệ JPA một-một, **liên kết tùy chọn** và **entity liên quan chưa tồn tại trong database** là hai vấn đề khác nhau. `@OneToOne(optional = true)` cho phép association mang `null`; `@JoinColumn(nullable = true)` và schema tương ứng xác định cách biểu diễn trạng thái ấy bằng khóa ngoại. Khi `account.profile` đã trỏ đến một **entity new/transient**, muốn lưu association hợp lệ phải persist entity đích tường minh hoặc sử dụng cascade persist phù hợp với vòng đời nghiệp vụ.

Một quan hệ tùy chọn không bao giờ có nghĩa database được phép lưu foreign key trỏ đến hàng không tồn tại. Foreign key và unique constraint bảo vệ tính toàn vẹn, còn transaction và cơ chế concurrency giúp xử lý những cập nhật đồng thời. Khi quan hệ hai hướng, cần cập nhật owning side và giữ object graph nhất quán; khi dùng `@MapsId`, phải hiểu rằng identity của entity phụ thuộc được gắn với entity cha.

Khi gặp tình huống “profile chưa có”, hãy xác định **đó là `null` hợp lệ, một object mới cần `persist`, hay một tham chiếu sai đến dữ liệu không tồn tại**. Từ sự phân biệt này, việc chọn schema, annotation, cascade, query và cách xử lý lỗi sẽ trở nên rõ ràng và an toàn hơn.
