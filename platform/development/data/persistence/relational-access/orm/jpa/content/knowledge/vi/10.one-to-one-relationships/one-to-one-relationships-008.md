# Lựa chọn một-một, đối tượng nhúng hoặc gộp cùng entity

Khi thiết kế một mô hình dữ liệu với JPA/Hibernate, hai nhóm thuộc tính có quan hệ rất chặt chẽ chưa chắc cần hai entity và một quan hệ `@OneToOne`. Đôi khi chúng chỉ tạo thành **một giá trị thuộc về entity khác**, thích hợp với `@Embeddable` và `@Embedded`. Có trường hợp đơn giản hơn nữa: các thuộc tính nên nằm thẳng trong cùng entity, không cần một kiểu Java riêng.

Ba lựa chọn thường gặp:

1. **Hai entity liên kết một-một bằng `@OneToOne`:** có hai đối tượng có identity riêng trong mô hình persistence, có thể có hai bảng và ràng buộc khóa ngoại duy nhất.
2. **Một entity chứa value object `@Embedded`:** có một entity với các thuộc tính được nhóm thành kiểu Java có ý nghĩa, thường lưu trong **cùng hàng của bảng owner**.
3. **Gộp thuộc tính vào cùng entity:** vẫn một entity, nhưng các field được khai báo trực tiếp mà không tạo lớp con.

Để chọn đúng, phải bắt đầu từ **identity, vòng đời, các bất biến nghiệp vụ, cách truy cập, ràng buộc database và khả năng mô hình thay đổi**, thay vì chỉ dựa vào việc trong sơ đồ có đúng một đối tượng A cho một đối tượng B.

## 1. Bài toán ví dụ: tài khoản, hồ sơ và địa chỉ

Giả sử xây ứng dụng quản lý tài khoản khách hàng, cần lưu:

- `Account`: ID, email, trạng thái tài khoản.
- `AccountProfile`: tên hiển thị, tiểu sử, ảnh đại diện; có thể được tạo sau khi khách hàng đăng ký.
- `Address`: đường phố, thành phố, mã bưu chính, quốc gia; một tài khoản có thể có địa chỉ thanh toán và giao hàng.
- `marketingOptIn`: lựa chọn nhận thông tin quảng bá, luôn là một phần của trạng thái tài khoản.

Ba phần thông tin bổ sung có những đặc điểm khác nhau:

| Thông tin | Câu hỏi nghiệp vụ | Lựa chọn ban đầu |
|---|---|---|
| Hồ sơ cá nhân | Hồ sơ có thể được tạo/xóa, quản lý riêng, có chính sách đọc/ghi riêng không? | Cân nhắc entity `AccountProfile` liên kết `@OneToOne` |
| Địa chỉ | Có cần ID độc lập hay chỉ là một giá trị gồm nhiều trường gắn với tài khoản? | `@Embeddable Address` và `@Embedded` |
| Lựa chọn marketing | Chỉ một cờ đơn giản, không cần một object có ngữ nghĩa riêng? | Field trực tiếp trong `Account` |

Những lựa chọn này **không loại trừ lẫn nhau**: cùng một `Account` có thể có hai `Address` được nhúng, một cờ `marketingOptIn` trực tiếp và một quan hệ một-một tới `AccountProfile`.

### 1.1. Quan hệ nghiệp vụ “một-một” không đủ để quyết định @OneToOne

Một tài khoản có **một cài đặt nhận email** không đồng nghĩa cài đặt đó phải là entity riêng. Một tài khoản có **một địa chỉ thanh toán** cũng chưa đủ để tạo bảng `addresses` với khóa chính độc lập. Nếu không có identity, vòng đời hoặc nhu cầu quản lý riêng, việc tạo entity con có thể chỉ làm tăng số bảng, join và mã đồng bộ.

Ngược lại, một hồ sơ có thể cần được tải riêng, tồn tại tùy chọn, có quyền truy cập hoặc vòng đời riêng. Khi đó một entity liên kết một-một có thể mang lại lợi ích thực sự.

## 2. Nhìn nhanh ba lựa chọn

| Tiêu chí | `@OneToOne` giữa hai entity | `@Embedded` value object | Field trực tiếp trong một entity |
|---|---|---|---|
| Số entity JPA | Hai | Một | Một |
| Entity con có `@Id` riêng? | Có, hoặc dùng shared primary key | Không | Không có entity con |
| Nơi lưu phổ biến | Hai bảng với FK unique hoặc shared PK | Cùng bảng owner | Cùng bảng owner |
| Có identity persistence độc lập? | Có cho cả hai entity | Không | Không |
| Có thể truy vấn trực tiếp như entity? | Có | Không tự đứng thành root entity JPQL | Truy vấn qua owner |
| Vòng đời | Có thể quản lý riêng hoặc cascade theo chính sách | Đi cùng owner | Đi cùng owner |
| Có thể gắn quan hệ entity riêng? | Có | Có một số mapping cho embeddable nhưng cần cân nhắc; không phải entity độc lập | Thuộc tính trên owner |
| Có thể tái sử dụng cấu trúc nhiều nơi? | Có, nhưng mỗi instance mang identity riêng | Rất phù hợp để tái sử dụng kiểu giá trị | Thường phải lặp lại field |
| Cần join để lấy dữ liệu? | Thường có nếu ở hai bảng | Không cần join riêng vì cùng hàng | Không |
| Khi phù hợp | Hai đối tượng có identity/lifecycle hoặc chính sách quản lý riêng | Nhóm thuộc tính tạo thành một giá trị có nghĩa | Vài thuộc tính đơn giản của chính entity |

Cần phân biệt **mô hình Java** và **mô hình quan hệ**. `@Embedded` và field gộp đều có thể tạo cùng một schema vật lý. `@OneToOne` thường dùng hai bảng, nhưng bản chất của annotation là quan hệ giữa **hai entity**, không phải lời hứa rằng một bảng thứ hai luôn bắt buộc trong mọi kiểu mapping.

## 3. Câu hỏi then chốt: đối tượng này có identity riêng không?

Trong JPA, entity có identity được xác định bằng kiểu entity và giá trị định danh theo `@Id` hoặc `@EmbeddedId`. Hai entity có thể được quản lý riêng trong persistence context.

Giả sử:

~~~java
Account account = entityManager.find(Account.class, 10L);
AccountProfile profile = entityManager.find(AccountProfile.class, 20L);
~~~

`AccountProfile` có entity identity riêng, thường tương ứng với một hàng trong bảng hồ sơ. Ngay cả khi mỗi tài khoản chỉ có tối đa một hồ sơ, đây vẫn là hai entity.

Trong khi đó:

~~~java
Account account = entityManager.find(Account.class, 10L);
Address billing = account.getBillingAddress();
~~~

Nếu `Address` là `@Embeddable`, `billing` **không có entity identity độc lập**. Không có lời gọi chuẩn như `entityManager.find(Address.class, ...)` vì `Address` không phải entity. Sự tồn tại của nó được diễn giải trong ngữ cảnh entity owner.

### 3.1. Kiểm tra bằng ngôn ngữ nghiệp vụ

Hãy thử các câu hỏi:

- “Hồ sơ của tài khoản A” có thể là một bản ghi quản trị riêng, được tạo sau, bị xóa hoặc audit độc lập không?
- “Địa chỉ thanh toán của tài khoản A” có phải là **một giá trị của A** hơn là một đối tượng cần ID riêng?
- “Người dùng đồng ý nhận marketing” có phải chỉ là một trạng thái của tài khoản?
- Đối tượng có xuất hiện trong API hoặc nghiệp vụ như tài nguyên với ID riêng không?
- Có thể thay toàn bộ đối tượng bằng giá trị mới mà không cần giữ lịch sử/identity của bản cũ không?

Nếu câu trả lời chủ yếu là “đây chỉ là giá trị của owner”, `@Embedded` hoặc field gộp thường đơn giản hơn. **Có nhiều thuộc tính không tự tạo ra nhu cầu entity identity**; một địa chỉ gồm sáu trường vẫn có thể là value object.

## 4. Lựa chọn thứ nhất: @OneToOne với hai entity

Giả sử `AccountProfile` được tạo sau khi đăng ký, có thể được sửa/xóa riêng. Mô hình database gồm hai bảng:

~~~text
accounts
+----+--------------------+--------+
| id | email              | status |
+----+--------------------+--------+
| 10 | a@example.com      | ACTIVE |
| 11 | b@example.com      | ACTIVE |
+----+--------------------+--------+

account_profiles
+----+------------+--------------+-----------------+
| id | account_id | display_name | bio             |
+----+------------+--------------+-----------------+
| 20 | 10         | An           | Java developer  |
+----+------------+--------------+-----------------+

accounts.id = 11 chưa có profile.
account_profiles.account_id tham chiếu accounts.id và UNIQUE.
~~~

Các ràng buộc quan trọng:

- Mỗi hồ sơ thuộc **đúng một tài khoản**: `account_id NOT NULL` và foreign key.
- Mỗi tài khoản có **tối đa một hồ sơ**: unique constraint trên `account_id`.
- Một tài khoản có thể **chưa có hồ sơ**: bảng `accounts` không nhất thiết có hàng tương ứng trong `account_profiles`.

Lưu ý: *one-to-one* thường là **một-đến-không-hoặc-một** từ phía tài khoản, nếu hồ sơ là tùy chọn. Unique foreign key không thể tự bảo đảm mọi hàng ở bảng cha đều có bản ghi con.

### 4.1. Schema với foreign key unique

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE account_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    bio VARCHAR(500),
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES accounts(id),
    CONSTRAINT uq_profile_account UNIQUE (account_id)
);
~~~

`account_profiles.id` là primary key của hồ sơ; `account_profiles.account_id` là foreign key **duy nhất**. Nếu thiếu `UNIQUE(account_id)`, database có thể nhận nhiều hồ sơ cùng tham chiếu một tài khoản; đó là quan hệ nhiều-một ở mức dữ liệu dù mã Java có khai báo `@OneToOne`.

### 4.2. Mapping JPA hai chiều

Code minh họa trong package `com.example.identity`:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(nullable = false)
    private String status;

    @OneToOne(
        mappedBy = "account",
        fetch = FetchType.LAZY,
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private AccountProfile profile;

    protected Account() {}

    public Account(String email) {
        this.email = email;
        this.status = "ACTIVE";
    }

    public AccountProfile createProfile(
        String displayName,
        String bio
    ) {
        if (profile != null) {
            throw new IllegalStateException("Đã có profile");
        }

        AccountProfile created =
            new AccountProfile(this, displayName, bio);

        this.profile = created;
        return created;
    }

    public AccountProfile getProfile() {
        return profile;
    }

    public Long getId() {
        return id;
    }
}
~~~

Entity hồ sơ:

~~~java
import jakarta.persistence.*;

@Entity
@Table(
    name = "account_profiles",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_profile_account",
        columnNames = "account_id"
    )
)
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

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(length = 500)
    private String bio;

    protected AccountProfile() {}

    AccountProfile(
        Account account,
        String displayName,
        String bio
    ) {
        this.account = account;
        this.displayName = displayName;
        this.bio = bio;
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
}
~~~

Các quyết định trong mapping:

1. **Phía sở hữu quan hệ** là `AccountProfile.account`, vì thuộc tính này có `@JoinColumn(name = "account_id")` và quản lý foreign key.
2. **Phía nghịch đảo** là `Account.profile` với `mappedBy = "account"`; không khai báo thêm một `@JoinColumn` khác trên phía này.
3. `optional = false` trên `AccountProfile.account` thể hiện hồ sơ phải có tài khoản; `nullable = false` tương ứng với ràng buộc cột.
4. `unique = true` và ràng buộc `UNIQUE(account_id)` của schema mới cưỡng chế “tối đa một hồ sơ” ở DB.
5. `cascade = ALL` cùng `orphanRemoval = true` mô tả chính sách cho hồ sơ phụ thuộc vòng đời tài khoản trong **ví dụ này**. Không tự dùng cùng cascade cho mọi quan hệ một-một.
6. `fetch = LAZY` là một yêu cầu/gợi ý chiến lược fetch; đặc biệt với phía nghịch đảo của one-to-one, hành vi lazy thực tế còn tùy provider và bytecode enhancement.

### 4.3. Duy trì hai phía của quan hệ

Trong quan hệ hai chiều, Java object graph cần nhất quán:

~~~java
Account account = new Account("a@example.com");
account.createProfile("An", "Java developer");

entityManager.persist(account);
~~~

`createProfile(...)` đặt `AccountProfile.account` và `Account.profile`. Nhờ cascade PERSIST từ tài khoản, `persist(account)` kéo theo hồ sơ. Nếu bỏ cascade, ứng dụng cần persist hồ sơ theo đúng thứ tự/transaction và quan hệ tương ứng.

**Database cập nhật foreign key dựa trên phía sở hữu.** Nếu chỉ đặt `account.profile = someProfile` ở phía `mappedBy`, nhưng `someProfile.account` không đúng, kết quả persist có thể khác mong muốn.

Khi hỗ trợ thay hoặc xóa profile, nên xây method nghiệp vụ thống nhất và giữ hai phía cùng thay đổi. `orphanRemoval = true` cho phép xóa entity con khi nó bị gỡ khỏi quan hệ sở hữu, nhưng cần xét cách provider xử lý thay thế đối tượng, flush, unique constraint và việc hồ sơ có thực sự thuộc vòng đời owner. Không dùng nó với đối tượng được chia sẻ hoặc cần giữ lịch sử độc lập.

### 4.4. Khi nào không nên cascade REMOVE?

Nếu profile được lưu để audit, hoặc entity liên kết có vòng đời độc lập, xóa tài khoản không nhất thiết được xóa profile ngay. Khi đó cần quy tắc ẩn danh hóa, soft delete, archive hoặc xử lý riêng.

Tương tự, nếu quan hệ một-một là `Employee → Office`, xóa nhân viên **không được xóa văn phòng** vì văn phòng không thuộc sở hữu vòng đời của nhân viên. `@OneToOne` không mang nghĩa mặc định “tự xóa object bên kia”.

## 5. Biến thể @OneToOne: shared primary key với @MapsId

Khi entity con chỉ tồn tại để mở rộng entity cha và không cần một chuỗi ID riêng, có thể dùng **shared primary key**: khóa chính của hồ sơ cũng là khóa ngoại trỏ tới tài khoản.

~~~text
accounts
  id = 10 (PRIMARY KEY)

account_profiles
  account_id = 10 (PRIMARY KEY + FOREIGN KEY -> accounts.id)
~~~

Schema ví dụ:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE account_profiles (
    account_id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    bio VARCHAR(500),
    CONSTRAINT fk_profile_account
        FOREIGN KEY (account_id) REFERENCES accounts(id)
);
~~~

Entity hồ sơ:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "account_profiles")
public class AccountProfile {
    @Id
    @Column(name = "account_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(length = 500)
    private String bio;

    protected AccountProfile() {}

    public AccountProfile(
        Account account,
        String displayName,
        String bio
    ) {
        this.account = account;
        this.displayName = displayName;
        this.bio = bio;
    }

    public Long getId() {
        return id;
    }
}
~~~

Với `@MapsId`, provider ánh xạ giá trị ID của hồ sơ từ khóa của `Account` được tham chiếu. **Không đặt thêm `@GeneratedValue` riêng cho ID hồ sơ** trong kiểu shared PK này.

Phía Account có thể giữ:

~~~java
@OneToOne(
    mappedBy = "account",
    cascade = CascadeType.ALL,
    orphanRemoval = true,
    fetch = FetchType.LAZY
)
private AccountProfile profile;
~~~

Cách shared PK có lợi khi:

- Hồ sơ không có ID tự sinh độc lập;
- quan hệ là một hồ sơ cho tối đa một account;
- muốn sử dụng một cột vừa làm PK vừa làm FK, không phải thêm cột `id` và `account_id UNIQUE`;
- vòng đời hồ sơ gắn mạnh với tài khoản.

Nhưng shared PK **vẫn là hai entity và hai bảng**. Cùng ID không biến profile thành `@Embeddable`. Nó cũng không bắt buộc mọi `Account` có profile: một account có thể không có hàng child tương ứng nếu schema và nghiệp vụ cho phép.

### 5.1. Chọn FK unique hay shared PK?

| Yếu tố | PK riêng + FK unique | Shared PK với `@MapsId` |
|---|---|---|
| PK của bảng con | `id` riêng | `account_id` vừa PK vừa FK |
| FK tới bảng cha | `account_id UNIQUE NOT NULL` | `account_id PRIMARY KEY REFERENCES ...` |
| ID của con | Có thể độc lập với ID cha | Cùng giá trị ID cha |
| Khi phù hợp | Con cần ID và khả năng tham chiếu riêng rõ ràng | Con là phần mở rộng định danh của cha |
| Độ phức tạp | Dễ hiểu khi hệ thống đã có PK riêng | Cần hiểu `@MapsId` và lifecycle cấp ID |
| Số bảng/nhu cầu join | Vẫn hai bảng | Vẫn hai bảng |

Nếu schema có sẵn PK riêng của profile, đừng vội đổi sang shared PK chỉ vì nó gọn hơn: việc đổi có thể ảnh hưởng foreign key ở các bảng khác và dữ liệu đã được tham chiếu bên ngoài.

## 6. Lựa chọn thứ hai: @Embeddable và @Embedded

Một **value object** thường được xác định bởi nội dung, không phải identity riêng. Ví dụ địa chỉ gồm đường, thành phố, mã bưu chính, quốc gia. Một địa chỉ trong tài khoản không nhất thiết là thực thể độc lập cần repository hoặc ID.

Khai báo:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(nullable = false, length = 200)
    private String street;

    @Column(nullable = false, length = 120)
    private String city;

    @Column(name = "postal_code", length = 30)
    private String postalCode;

    @Column(name = "country_code", nullable = false, length = 2)
    private String countryCode;

    protected Address() {}

    public Address(
        String street,
        String city,
        String postalCode,
        String countryCode
    ) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
        this.countryCode = countryCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public String getCountryCode() {
        return countryCode;
    }
}
~~~

`@Embeddable` đánh dấu một lớp dùng làm component/giá trị được nhúng. Nó **không có `@Entity` và không có `@Id`**. Lớp này có thể có constructor không tham số `protected` để provider khởi tạo, cùng constructor nghiệp vụ để sử dụng trong code.

Trong `Account`:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street", length = 200)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city", length = 120)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code", length = 30)
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "billing_country_code", length = 2)
    )
})
private Address billingAddress;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "shipping_street", length = 200)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "shipping_city", length = 120)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "shipping_postal_code", length = 30)
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "shipping_country_code", length = 2)
    )
})
private Address shippingAddress;
~~~

Đoạn trên là phần field bổ sung của entity `Account`, không phải một class mới độc lập.

**Tại sao cần `@AttributeOverride`?** Vì cùng kiểu `Address` được dùng hai lần. Nếu provider mặc định dùng cùng tên cột `street`, `city` cho cả hai, sẽ bị xung đột hoặc mapping mơ hồ. Override cho phép ánh xạ cùng cấu trúc Java tới các nhóm cột riêng.

### 6.1. Schema khi sử dụng embedded

Các trường của cả hai `Address` nằm **trong một bảng `accounts`**:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,

    billing_street VARCHAR(200),
    billing_city VARCHAR(120),
    billing_postal_code VARCHAR(30),
    billing_country_code VARCHAR(2),

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code VARCHAR(2)
);
~~~

Schema trên cho phép địa chỉ tùy chọn nên các cột đều nullable. Nếu muốn một địa chỉ là bắt buộc, cần thiết kế constraint và validation tương ứng; không lấy mặc định `nullable = false` trong ví dụ `Address` rồi kỳ vọng cùng class có thể vừa bắt buộc vừa tùy chọn khi dùng nhiều lần. Có thể dùng `@AttributeOverride` phù hợp, Bean Validation và ràng buộc database rõ ràng theo từng nhóm field.

Ở một số provider, một component có tất cả cột null có thể được khôi phục thành `null` thay vì một instance `Address` rỗng. Không nên dựa vào chi tiết khôi phục “toàn null” nếu quy tắc nghiệp vụ cần phân biệt một địa chỉ rỗng với không có địa chỉ.

### 6.2. Vì sao embedded không phải @OneToOne?

Với `Address` nhúng:

- Không có bảng `addresses` riêng chỉ vì dùng `@Embedded`.
- Không có primary key hay foreign key để trỏ đến địa chỉ như một entity.
- Không thể gọi `entityManager.find(Address.class, id)`.
- Không có lifecycle `persist/remove` độc lập cho Address.
- Khi owner được tải, các cột địa chỉ là một phần của hàng owner, không có join sang bảng component.
- Việc sửa địa chỉ tạo thay đổi trạng thái của **Account**, được provider đồng bộ khi transaction flush.

Ví dụ cập nhật:

~~~java
Account account = em.find(Account.class, accountId);

// Phương thức nghiệp vụ đặt giá trị Address mới trên Account.
account.changeShippingAddress(
    new Address("12 Nguyen Hue", "Ho Chi Minh City", "700000", "VN")
);
~~~

Ví dụ giả định `Account` có method `changeShippingAddress(Address)` thay thế giá trị thuộc tính nhúng. Đây là cách tiếp cận dễ kiểm soát: value object được thay nguyên khối khi địa chỉ thay đổi, thay vì phát sinh ID mới hoặc lưu component độc lập.

### 6.3. Truy vấn trường nằm trong embeddable

JPQL có thể điều hướng theo đường thuộc tính:

~~~java
List<Account> accounts = em.createQuery(
        """
        SELECT a FROM Account a
        WHERE a.billingAddress.city = :city
        """,
        Account.class
    )
    .setParameter("city", "Ho Chi Minh City")
    .getResultList();
~~~

Tại tầng SQL, provider có thể truy vấn trực tiếp cột `billing_city` của bảng `accounts`. `Address` không trở thành JPQL root entity được truy vấn bằng `FROM Address a`.

### 6.4. Value object nên có ngữ nghĩa giá trị

Một `Address` thường có ý nghĩa theo nội dung: hai địa chỉ có cùng đường, thành phố, mã bưu chính và quốc gia có thể được coi là bằng nhau theo quy tắc nghiệp vụ. Trong Java, có thể định nghĩa `equals()` và `hashCode()` theo các trường ổn định khi thiết kế value object.

Không tự áp dụng cách so sánh theo ID của entity lên Address vì Address **không có ID**. Đối với embeddable JPA, nếu viết class bất biến ở tầng nghiệp vụ, cần bảo đảm provider vẫn có cơ chế khởi tạo/đọc field hợp lệ theo phiên bản hỗ trợ. Không dùng constructor chỉ có tham số mà quên điều kiện khởi tạo cần thiết cho provider.

### 6.5. @EmbeddedId cũng dùng embeddable, nhưng mục đích khác

JPA còn có `@EmbeddedId` để ánh xạ **khóa chính ghép**:

~~~java
@Embeddable
public class EnrollmentId implements Serializable {
    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {}

    // equals, hashCode theo hai thành phần và các accessor...
}

@Entity
public class Enrollment {
    @EmbeddedId
    private EnrollmentId id;
}
~~~

`EnrollmentId` là embeddable về mặt cú pháp, nhưng được dùng làm **ID của entity Enrollment**. Điều này khác với `@Embedded Address` thường dùng để nhóm các thuộc tính giá trị thông thường.

Không nhầm `@Embedded` dùng value object với `@MapsId` dùng chung khóa của hai entity trong quan hệ một-một.

## 7. Lựa chọn thứ ba: gộp các thuộc tính trong cùng entity

Không phải mọi nhóm field đều cần một class `@Embeddable`. Nếu thuộc tính nhỏ, được đọc và sửa cùng entity, không có khái niệm giá trị độc lập, khai báo trực tiếp sẽ dễ hiểu.

Ví dụ trong `Account`:

~~~java
@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(name = "marketing_opt_in", nullable = false)
    private boolean marketingOptIn;

    @Column(name = "preferred_language", length = 10)
    private String preferredLanguage;

    protected Account() {}

    public Account(String email) {
        this.email = email;
        this.marketingOptIn = false;
        this.preferredLanguage = "vi";
    }

    public void changeMarketingConsent(boolean consent) {
        this.marketingOptIn = consent;
    }

    public void changePreferredLanguage(String language) {
        this.preferredLanguage = language;
    }
}
~~~

Trong schema:

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    preferred_language VARCHAR(10)
);
~~~

Hai trường `marketingOptIn` và `preferredLanguage` là dữ liệu thuộc tài khoản, không cần identity riêng, quan hệ SQL hay value object nếu nghiệp vụ chưa có nhu cầu gom chúng.

### 7.1. Vậy lúc nào gộp, lúc nào @Embedded?

Cả hai có thể dùng cùng schema nhưng tác động khác tới cấu trúc Java:

| Trường hợp | Field trực tiếp | `@Embedded` |
|---|---|---|
| Một cờ `marketingOptIn` | Gọn và rõ | Có thể quá phức tạp |
| Hai trường đơn giản không tạo một khái niệm domain | Hợp lý | Chưa cần thiết |
| Địa chỉ có bốn đến sáu thành phần | Entity nhiều field liên quan | Có một kiểu `Address` rõ nghĩa |
| Hai địa chỉ billing/shipping cùng cấu trúc | Phải nhân đôi field và method | Tái sử dụng một `Address` và override tên cột |
| Cần validation và thao tác như `address.isValidForShipping()` | Logic dễ rải rác trong owner | Có thể gom logic vào value object |
| Cần thay cả nhóm như một giá trị | Nhiều setter gây trạng thái dở dang | Có thể thay object nhúng bằng một thao tác |
| Cần dùng trong nhiều entity | Dễ lặp lại | Embeddable tái sử dụng được |

Điểm quyết định không phải số lượng field tuyệt đối, mà là **nhóm thuộc tính có cùng tạo thành một khái niệm domain cần được đặt tên và bảo vệ bất biến hay không**.

Ví dụ `Money(amount, currency)` có thể là value object, vì một số tiền thường có ý nghĩa khi đi kèm loại tiền tệ. Nhưng hai trường audit `lastEditedBy` và `lastEditedAt` có thể để trực tiếp nếu phạm vi dự án nhỏ và không cần abstraction riêng.

## 8. So sánh ba lựa chọn bằng cùng một use case

Giả sử yêu cầu: “Mỗi tài khoản có thể lưu một địa chỉ liên hệ gồm street và city.”

### Phương án A: entity riêng @OneToOne

~~~text
accounts                  contact_addresses
+----+------------+        +----+------------+--------+------+
| id | email      |        | id | account_id | street | city |
+----+------------+        +----+------------+--------+------+
| 10 | a@ex.com   | <----- | 70 | 10         | ...    | ...  |
+----+------------+        +----+------------+--------+------+
                               account_id UNIQUE NOT NULL
~~~

Mã Java:

~~~java
@Entity
class ContactAddress {
    @Id
    @GeneratedValue
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", unique = true, nullable = false)
    private Account account;

    private String street;
    private String city;
}
~~~

Phù hợp nếu địa chỉ là **tài nguyên có ID riêng**, thay đổi/được xác thực độc lập hoặc phục vụ nhiều workflow. Nhưng phải quản lý hai entity, ràng buộc unique, cascade, transaction và join.

### Phương án B: value object @Embedded

~~~text
accounts
+----+------------+----------------+--------------+
| id | email      | contact_street | contact_city |
+----+------------+----------------+--------------+
| 10 | a@ex.com   | ...            | ...          |
+----+------------+----------------+--------------+
~~~

Mã Java:

~~~java
@Embeddable
class ContactAddress {
    private String street;
    private String city;

    protected ContactAddress() {}
}

@Entity
class Account {
    @Id
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "contact_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "contact_city")
        )
    })
    private ContactAddress contactAddress;
}
~~~

Phù hợp khi địa chỉ là **một giá trị thuộc tài khoản**. Không có bảng địa chỉ riêng; thay address là thay trạng thái Account.

### Phương án C: field trực tiếp

~~~java
@Entity
class Account {
    @Id
    private Long id;

    @Column(name = "contact_street")
    private String contactStreet;

    @Column(name = "contact_city")
    private String contactCity;
}
~~~

Có thể tạo đúng **cùng cấu trúc bảng** như B. Phù hợp khi chỉ vài field và không muốn thêm abstraction Java. Nếu sau này xuất hiện nhiều địa chỉ, validation phức tạp hoặc sử dụng cùng kiểu trong các entity khác, có thể refactor thành embeddable.

### 8.1. Điều gì thực sự thay đổi?

- Chuyển từ **C sang B** chủ yếu là refactor mô hình Java nếu giữ nguyên tên/kiểu cột: nhóm field thành `@Embeddable` và cấu hình `@AttributeOverride`; database không nhất thiết phải đổi.
- Chuyển từ **B/C sang A** là thay đổi schema và lifecycle: tách cột sang bảng mới, tạo FK/unique, migrate dữ liệu và thay cách truy cập.
- Chuyển từ **A sang B/C** cần gộp dữ liệu của bảng con vào bảng cha, xử lý account không có record con, xác minh uniqueness rồi điều chỉnh truy vấn.

## 9. Một-một có thực sự là một-một không?

Trong database quan hệ, một hàng con có FK tới một hàng cha **không tự tạo quan hệ 1:1**. Nếu FK không unique:

~~~sql
CREATE TABLE account_profiles (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id)
);
~~~

Hai hồ sơ vẫn có thể cùng `account_id = 10`. Muốn tối đa một hồ sơ:

~~~sql
ALTER TABLE account_profiles
ADD CONSTRAINT uq_profile_account UNIQUE (account_id);
~~~

Với shared PK:

~~~sql
CREATE TABLE account_profiles (
    account_id BIGINT PRIMARY KEY REFERENCES accounts(id)
);
~~~

Cột `account_id` đồng thời là PK nên mặc nhiên unique.

### 9.1. optional=false và nullable=false khác nhau

- `@OneToOne(optional = false)` mô tả association phải có giá trị ở mức mô hình JPA/provider.
- `@JoinColumn(nullable = false)` mô tả tính không-null của cột join trong mapping/DDL.
- `NOT NULL` ở database là ràng buộc vật lý thực tế.
- `UNIQUE` ở database bảo đảm một account không có hai profile.

Ngay cả khi tất cả các điều kiện trên được đặt ở phía `AccountProfile.account`, **không có ràng buộc đơn giản nào bắt buộc mọi Account phải có một Profile**. Muốn “mỗi Account phải có chính xác một Profile”, cần thiết kế thêm quy tắc tạo đồng thời, validation hoặc cơ chế ràng buộc thích hợp.

### 9.2. Một-một trong nghiệp vụ có thể thay đổi thành một-nhiều

Ví dụ “một tài khoản có đúng một địa chỉ giao hàng” hôm nay, nhưng sáu tháng sau cần nhiều địa chỉ đã lưu. Nếu địa chỉ là entity có identity riêng từ đầu, chuyển sang `@OneToMany` có thể thuận lợi về mô hình. Nếu nó là embedded, cần chuyển dữ liệu sang bảng `addresses` và tạo quan hệ mới.

Không có đáp án mặc định cho mọi dự án: hãy cân nhắc **khả năng nhiều giá trị phát sinh thật sự** và chi phí phải trả hiện tại. Đừng tạo bảng/entity riêng cho mọi thuộc tính chỉ dựa vào giả thuyết có thể mở rộng.

## 10. Ảnh hưởng tới fetch và hiệu năng truy vấn

### 10.1. @OneToOne có thể phát sinh join hoặc truy vấn bổ sung

Nếu profile nằm ở bảng riêng, việc lấy account cùng profile thường cần join hoặc một truy vấn tiếp theo.

Ví dụ JPQL chủ động tải profile:

~~~java
Account account = em.createQuery(
        """
        SELECT a
        FROM Account a
        LEFT JOIN FETCH a.profile
        WHERE a.id = :id
        """,
        Account.class
    )
    .setParameter("id", accountId)
    .getSingleResult();
~~~

Đây là một truy vấn cụ thể được thiết kế cho màn hình cần profile. Với màn hình chỉ cần email, không nhất thiết phải tải mọi thông tin profile.

Tuy nhiên, **`fetch = FetchType.LAZY` trên `@OneToOne` không phải bảo đảm SQL sẽ luôn trì hoãn**. Đặc biệt ở phía `mappedBy`, provider có thể phải kiểm tra xem bản ghi con có tồn tại hay không, hoặc cần cơ chế bytecode enhancement để trì hoãn hiệu quả tùy cấu hình. Với Hibernate, cần quan sát SQL thực tế thay vì suy ra từ annotation.

### 10.2. Embedded và field trực tiếp cùng hàng dữ liệu

Một `Address` được nhúng và các field trực tiếp có chung đặc điểm: dữ liệu thường nằm trên hàng `accounts`. Vì vậy, tải owner có thể kéo theo các cột ấy trong câu SELECT tương ứng, dù caller không sử dụng.

Nếu bảng có rất nhiều cột lớn ít được dùng, một entity/table riêng có thể hữu ích cho tách dữ liệu và tối ưu truy vấn. Nhưng đó không phải lý do đủ để mặc định một-một **luôn nhanh hơn**: split table tạo join, kế hoạch truy vấn, index và chi phí ghi khác nhau. Cần đo workload thực tế.

### 10.3. Projection/DTO để kiểm soát lượng dữ liệu

Cho màn hình chỉ hiển thị email và tên hiển thị, có thể dùng projection:

~~~java
public record AccountSummary(Long id, String email, String displayName) {}

List<AccountSummary> rows = em.createQuery(
        """
        SELECT new com.example.dto.AccountSummary(
            a.id,
            a.email,
            p.displayName
        )
        FROM Account a
        LEFT JOIN a.profile p
        """,
        AccountSummary.class
    )
    .getResultList();
~~~

Ví dụ giả định `AccountSummary` được khai báo trong package `com.example.dto`. Projection cho phép lấy đúng trường cần hiển thị thay vì tải cả entity graph. Tùy provider và mapping, đường truy vấn có thể khác; vẫn nên kiểm tra SQL và execution plan.

### 10.4. @Basic(fetch = LAZY) không biến field gộp thành bảng độc lập

Một số developer muốn trì hoãn một trường lớn trong cùng bảng bằng:

~~~java
@Basic(fetch = FetchType.LAZY)
private String biography;
~~~

Đây thường là một gợi ý cho provider, có thể đòi hỏi bytecode enhancement và không bảo đảm luôn tránh tải cột. Nó không tạo nên lifecycle hoặc identity độc lập giống hai entity `@OneToOne`. Nếu vấn đề chính là dữ liệu lớn ít dùng, hãy đánh giá thiết kế bảng và truy vấn, không chỉ đổi annotation.

## 11. Transaction, dirty checking và concurrency

### 11.1. Với field trực tiếp hoặc @Embedded

Khi `Account` là managed, sửa field trực tiếp hoặc thay `Address` nhúng sẽ thay đổi trạng thái của **Account**. Provider dùng dirty checking để đồng bộ các cột tương ứng vào bảng owner trong transaction.

~~~java
@Transactional
public void changeShippingAddress(
    Long accountId,
    Address newAddress
) {
    Account account = repository.findById(accountId)
        .orElseThrow();

    account.changeShippingAddress(newAddress);
    // Đổi trạng thái Account; không cần persist một Address riêng.
}
~~~

Ví dụ dùng `@Transactional` của Spring và giả định entity có method nghiệp vụ. `@Embedded` không cần `CascadeType.PERSIST` từ Account sang Address vì Address không phải entity.

Nếu `Account` có `@Version`, các thay đổi thuộc tính nhúng thường nằm trong cơ chế optimistic locking của cùng owner.

### 11.2. Với @OneToOne

`Account` và `AccountProfile` là **hai entity riêng**. Nếu sửa profile, dirty checking áp dụng cho `AccountProfile` managed; bảng profile có thể được UPDATE độc lập với bảng account. Nếu có version:

~~~java
@Entity
class AccountProfile {
    @Id
    private Long id;

    @Version
    private long version;

    private String displayName;
}
~~~

Version trên profile giúp phát hiện xung đột cập nhật **profile**, nhưng không tự bảo đảm các thay đổi trên Account và Profile luôn cùng một version domain. Nếu thao tác nghiệp vụ cần bất biến bắc qua cả hai entity, phải tổ chức transaction/locking phù hợp; không nên cho rằng có `@OneToOne` thì mọi cập nhật đều tự động dùng chung optimistic lock.

Hai bảng vẫn có thể được ghi trong **cùng một transaction database** qua một EntityManager khi cấu hình đúng. Tách entity không đồng nghĩa bắt buộc tách transaction hoặc microservice.

## 12. Xóa, thay thế và quản lý vòng đời

Một giá trị embedded được thay:

~~~java
account.changeBillingAddress(
    new Address("1 Le Loi", "Ho Chi Minh City", "700000", "VN")
);
~~~

Không có entity Address cũ cần `remove()`. Các cột thuộc Account được cập nhật theo transaction.

Với one-to-one, cần chọn rõ:

| Quan hệ nghiệp vụ | Cấu hình vòng đời thường cần xem xét |
|---|---|
| Profile không thể tồn tại nếu Account bị xóa | Có thể cascade PERSIST/REMOVE và orphanRemoval theo quy tắc thực tế |
| Profile cần giữ lịch sử sau khi tài khoản bị vô hiệu hóa | Không tự xóa; cân nhắc soft delete, archive và chính sách dữ liệu |
| Tham chiếu tới đối tượng độc lập như phòng làm việc | Không cascade REMOVE sang đối tượng độc lập |
| Hồ sơ có thể thay thế bằng entity khác | Xác định semantics của replace, khóa unique, orphanRemoval và flush order |
| Account có thể không có Profile | Thiết kế optional và truy vấn LEFT JOIN phù hợp |

**Không dùng `CascadeType.ALL` như một mặc định vô điều kiện cho mọi `@OneToOne`.** Cascade là lựa chọn về vòng đời, cần căn cứ quyền sở hữu nghiệp vụ chứ không phải chỉ theo bội số.

## 13. Tác động tới schema migration

### 13.1. Từ field gộp sang @Embedded

Nếu hai field `billingCity` và `billingStreet` đang được lưu ở `billing_city`, `billing_street`, có thể tạo `Address` rồi override tên cột đúng như cũ.

~~~text
Trước:
Account.billingStreet -> accounts.billing_street
Account.billingCity   -> accounts.billing_city

Sau:
Account.billingAddress.street -> accounts.billing_street
Account.billingAddress.city   -> accounts.billing_city
~~~

Ở trường hợp này schema có thể giữ nguyên. Nhưng phải thay code truy cập, JPQL/Spring Data repository property path, serialization DTO và validation tương ứng.

### 13.2. Từ @Embedded sang @OneToOne

Nếu cần biến địa chỉ thành entity riêng, các bước phổ biến là:

1. Thiết kế bảng con có PK/FK và UNIQUE theo quan hệ mới.
2. Thêm bảng cùng index, constraint và quy tắc nullability.
3. Backfill dữ liệu từ các cột trên bảng Account sang bảng con.
4. Xác định những Account chưa có địa chỉ và cách biểu diễn trạng thái không có bản ghi con.
5. Cập nhật mapping, repository, transaction, query và các API đọc/ghi.
6. Trong giai đoạn chuyển đổi, nếu hai phiên bản ứng dụng cùng chạy, định nghĩa chiến lược đọc/ghi để không mất dữ liệu.
7. Chỉ bỏ cột cũ sau khi xác thực luồng dữ liệu mới và hoàn tất migration có kiểm soát.

Không chỉ thêm `@OneToOne` rồi kỳ vọng Hibernate tự di chuyển dữ liệu giữa hai bảng. Schema auto-update không thay thế data migration.

### 13.3. Từ @OneToOne sang gộp cùng entity

Cần chuyển cột từ bảng Profile sang bảng Account, giải quyết hàng Profile không có hoặc dữ liệu không đồng nhất. Nếu có FK ở các bảng khác tham chiếu `AccountProfile.id`, phải xử lý các quan hệ đó trước khi xóa bảng con.

Nếu hồ sơ từng có ID công khai, việc xóa entity riêng có thể thay đổi contract API hoặc log/audit. Đây là **thay đổi mô hình identity**, không đơn thuần là đổi tên field Java.

### 13.4. Đừng để @OneToOne thay cho constraint database

Dù mapping có `@JoinColumn(unique = true)`, môi trường production có thể tắt Hibernate DDL generation và quản lý schema bằng Flyway/Liquibase. Khi đó chính migration phải thực sự tạo UNIQUE/FK/NOT NULL cần thiết.

## 14. Null, optional và dữ liệu không đầy đủ

Địa chỉ có thể vắng mặt toàn bộ hoặc chỉ thiếu một số trường. Mô hình cần phân biệt hai trường hợp.

Với `@Embedded`:

~~~java
@Embedded
private Address billingAddress; // Có thể null nếu nghiệp vụ cho phép.
~~~

Nếu toàn bộ cột địa chỉ trong DB là NULL, một số provider có thể trả `null` thay vì object Address có các field null. Vì vậy, nếu ứng dụng cần phân biệt “chưa nhập địa chỉ” với “địa chỉ đã tạo nhưng thiếu thông tin”, hãy thiết kế trạng thái riêng thay vì dựa vào việc provider có khởi tạo embedded object rỗng.

Với `@OneToOne`:

~~~java
@OneToOne(mappedBy = "account")
private AccountProfile profile;
~~~

Không có hàng trong `account_profiles` nghĩa là chưa có Profile. Cách này thể hiện một trạng thái tùy chọn rõ ở cấu trúc dữ liệu, nhưng kéo theo chi phí quản lý bảng/quan hệ.

Với field gộp:

~~~java
private String billingStreet;
private String billingCity;
~~~

Cả hai null cũng có thể nghĩa là chưa có địa chỉ, nhưng nếu chỉ một trường null, cần validation nghiệp vụ để tránh trạng thái dở dang. Đóng gói thành `Address` có thể giúp kiểm soát bất biến này ở tầng Java, dù schema vẫn phải có constraint thích hợp.

## 15. Quan hệ một-một và bảo mật dữ liệu

Tách bảng `account_profiles` khỏi `accounts` có thể hữu ích nếu các nhóm dữ liệu có yêu cầu truy cập hoặc vận hành khác nhau. Ví dụ chứa thông tin nhạy cảm, có thể cần phân quyền đọc ở mức database/table, schema hoặc service.

Tuy nhiên, **tách bảng không tự tạo ranh giới bảo mật**. Nếu cùng application user vẫn có quyền đọc cả hai bảng, nếu API trả quá nhiều trường, hoặc nếu log ghi nội dung nhạy cảm, dữ liệu vẫn có thể bị lộ.

Tương tự, gộp trong một entity không tự đồng nghĩa mọi API phải trả toàn bộ field. Có thể dùng DTO/projection, authorization và chính sách logging phù hợp. Quyết định bảo mật cần được thiết kế trực tiếp, không suy từ `@OneToOne` hay `@Embedded`.

## 16. Checklist quyết định cho bài toán thực tế

Trước khi thêm một `@OneToOne`, hãy trả lời các câu hỏi:

1. **Đối tượng con có identity độc lập không?** Có cần ID riêng, history, repository, API resource hoặc lifecycle tách biệt?
2. **Nó có thể tồn tại nếu owner biến mất không?** Nếu có, không nên mặc định cascade REMOVE/orphanRemoval.
3. **Thông tin có được đọc/ghi cùng owner gần như mọi lúc không?** Nếu có, bảng riêng có thể làm tăng join không cần thiết.
4. **Nhóm thuộc tính có tạo thành một giá trị domain có nghĩa không?** Nếu có, cân nhắc `@Embeddable`.
5. **Giá trị có thể tái sử dụng ở nhiều nơi không?** Một `Address` có thể dùng cho billing và shipping trong cùng entity.
6. **Chỉ là một hoặc hai thuộc tính đơn giản?** Có thể gộp thẳng vào entity.
7. **Có cần bảo đảm một-một ở database không?** Nếu dùng hai bảng, phải có UNIQUE FK hoặc shared PK thực sự.
8. **Đối tượng có thể không tồn tại không?** Thiết kế 0..1, nullability và cách query phù hợp.
9. **Có cần thay đổi bội số sang 1..n trong tương lai gần không?** Cân nhắc chi phí migration với dữ liệu thật.
10. **Truy vấn phổ biến cần những trường nào?** Xem xét JOIN FETCH, projection, indexing, N+1 và lazy one-to-one thực tế.
11. **Có cần versioning/transaction độc lập không?** Entity riêng có thể có `@Version` riêng nhưng bất biến xuyên hai entity vẫn cần transaction.
12. **Schema hiện có và chi phí migration thế nào?** Đừng thay đổi identity, constraint, API hoặc quan hệ đã triển khai mà không tính đến dữ liệu lịch sử.

### 16.1. Cây quyết định đơn giản

~~~text
Thông tin bổ sung cho Account
          |
          v
Có identity/lifecycle/quyền quản lý riêng?
     |                        |
    Có                       Không
     |                        |
     v                        v
  @OneToOne             Có tạo thành value object
  + DB UNIQUE FK         có ý nghĩa, cần tái sử dụng
  hoặc shared PK          hoặc bảo vệ bất biến?
                           |             |
                          Có            Không
                           |             |
                           v             v
                       @Embedded       Field trực tiếp
                       @Embeddable     trong Account
~~~

Cây trên là hướng dẫn khởi đầu. Những yếu tố như performance thực tế, schema hiện có, ràng buộc production, security và thay đổi nghiệp vụ có thể khiến quyết định cuối khác đi.

## 17. Tình huống tự luyện

### Tình huống A: ngày sinh và tên hiển thị

Mỗi `Customer` có `birthDate` và `displayName`. Chúng không có ID hay vòng đời riêng, thường được cập nhật cùng customer. Chọn phương án nào?

**Gợi ý:** field trực tiếp trong Customer thường đủ. Không tạo `@OneToOne CustomerDetails` nếu chưa có yêu cầu nghiệp vụ hoặc kiến trúc khác.

### Tình huống B: hai loại địa chỉ

Một `Account` có `billingAddress` và `shippingAddress`, mỗi cái gồm street, city, postalCode, countryCode. Hai giá trị có cấu trúc và validation giống nhau, không cần ID.

**Gợi ý:** dùng `@Embeddable Address` hai lần với `@Embedded` và `@AttributeOverride`. Schema có hai nhóm cột; không có bảng Address độc lập.

### Tình huống C: hồ sơ phụ có thể tạo sau

Một `Account` được tạo ngay lúc đăng ký, nhưng `Profile` chỉ được tạo khi hoàn thiện thông tin. Mỗi Account tối đa một Profile, và Profile được quản lý riêng.

**Gợi ý:** `@OneToOne` với bảng Profile có unique FK hoặc shared PK; phân biệt 0..1 và 1..1. Nếu profile thật sự là phần phụ thuộc, có thể cân nhắc `@MapsId`.

### Tình huống D: thẻ nhân viên và phòng ban

Mỗi nhân viên đang được gán một thẻ ra vào, thẻ có mã định danh vật lý riêng, ngày cấp và vòng đời thu hồi; mỗi thẻ chỉ thuộc một nhân viên ở một thời điểm.

**Gợi ý:** có cơ sở để dùng entity `AccessCard` riêng với quan hệ một-một, vì thẻ có identity và workflow riêng. Không cascade REMOVE thẻ một cách vô điều kiện nếu thẻ cần được ghi nhận lịch sử/thu hồi.

### Tình huống E: người dùng có nhiều số điện thoại

Hệ thống ban đầu lưu một `phoneNumber`, sau đó yêu cầu nhiều số, mỗi số có thể được xác thực và đặt làm mặc định.

**Gợi ý:** yêu cầu mới không còn là một-một. Cân nhắc entity `PhoneNumber` một-nhiều, hoặc `@ElementCollection` nếu thật sự chỉ là tập giá trị không có identity riêng. Đừng ép dữ liệu nhiều-số vào một field chuỗi phân tách dấu phẩy.

### Tình huống F: bảng hồ sơ đã có shared PK

Có hai bảng `users(id PK)` và `user_profiles(user_id PK FK -> users.id)`. Chọn annotation nào trong JPA?

**Gợi ý:** `@OneToOne` kèm `@MapsId` trên entity UserProfile; không thêm IDENTITY riêng trên child.

## 18. Ghi nhớ khi lựa chọn

- **`@OneToOne` dành cho quan hệ giữa hai entity**, có identity riêng ở tầng JPA. Dùng UNIQUE FK hoặc shared PK để thực thi “tối đa một” ở database.
- **`@Embeddable` và `@Embedded` dành cho nhóm thuộc tính có ngữ nghĩa giá trị**, không có entity ID; các cột thường nằm cùng bảng owner.
- **Gộp trực tiếp vào entity** phù hợp với các thuộc tính nhỏ, ít logic riêng, không cần một value object độc lập.
- **Bội số một-một không đủ để chọn annotation.** Phải xét identity, lifecycle, optionality, transaction, cách truy vấn và schema.
- `mappedBy` mô tả phía nghịch đảo; phía có `@JoinColumn` mới nắm cột foreign key.
- `cascade` và `orphanRemoval` thể hiện quyền sở hữu vòng đời, **không phải tính năng bắt buộc của mọi `@OneToOne`**.
- Shared PK với `@MapsId` vẫn là hai entity; nó khác `@Embedded`.
- `fetch = LAZY` trên quan hệ một-một có giới hạn phụ thuộc provider; phải quan sát SQL thực tế.
- Chuyển giữa ba lựa chọn có thể thay đổi identity, số bảng, API và dữ liệu lịch sử; cần migration có kiểm soát khi schema thay đổi.

Trong thiết kế JPA, **entity identity dùng để quản lý thực thể, value object dùng để diễn đạt giá trị, còn field trực tiếp diễn đạt trạng thái đơn giản của chính thực thể**. Chọn đúng mô hình giúp dữ liệu phản ánh nghiệp vụ, giảm join và cascade không cần thiết, đồng thời giữ được không gian mở rộng khi vòng đời hoặc quan hệ thật sự thay đổi.
