# Ánh xạ nhiều bảng cho một thực thể bằng bảng phụ trong Hibernate

Một thực thể nghiệp vụ không nhất thiết được lưu trong đúng một bảng quan hệ. Chẳng hạn, ứng dụng quản lý tài khoản khách hàng có thể lưu định danh, email và trạng thái vào bảng `customer_account`, trong khi tên hiển thị, số điện thoại và địa chỉ nằm ở bảng `customer_profile`. Trong Java, tất cả vẫn là thuộc tính của **một đối tượng `CustomerAccount`**, có một khóa định danh, một vòng đời managed/detached và cùng được Hibernate theo dõi thay đổi.

Trong Jakarta Persistence (JPA) và Hibernate, cách ánh xạ này được biểu đạt bằng **`@SecondaryTable`** (một bảng phụ) hoặc **`@SecondaryTables`** (nhiều bảng phụ). Hibernate sử dụng metadata để biết thuộc tính nào nằm ở bảng chính, thuộc tính nào nằm ở bảng phụ, cách nối các bản ghi theo khóa chính và cách phát sinh SQL khi đọc, thêm, sửa hoặc xóa thực thể.

Đây là kỹ thuật **vertical partitioning ở cấp ánh xạ entity**: tách các nhóm cột thành nhiều bảng cùng chia sẻ định danh. Bài này giải thích cú pháp, mô hình khóa chính–khóa ngoại, cách Hibernate thực thi SQL và những lựa chọn thiết kế có thể ảnh hưởng tính đúng đắn, hiệu năng và khả năng bảo trì.

> **Phạm vi:** Ví dụ sử dụng `jakarta.persistence` và Hibernate ORM 6.x. Các quy tắc ánh xạ chuẩn JPA nhìn chung tương tự ở các phiên bản Hibernate khác, nhưng cách Hibernate tải bảng phụ, phát sinh các câu SQL, xử lý bản ghi bảng phụ không tồn tại và các annotation mở rộng của Hibernate có thể thay đổi theo phiên bản. SQL minh họa dùng PostgreSQL; cú pháp DDL cần điều chỉnh nếu sử dụng Oracle, MySQL hoặc DBMS khác.

## 1. Vì sao một thực thể có thể nằm ở nhiều bảng?

Giả sử màn hình tài khoản thường xuyên hiển thị email và trạng thái, còn thông tin hồ sơ chi tiết chỉ được sử dụng trong một số nghiệp vụ. Có thể tổ chức dữ liệu như sau:

~~~text
customer_account                         customer_profile
+-------------------------+              +---------------------------+
| id            PK        |<-------------| account_id      PK, FK   |
| email         UNIQUE    |   1 : 0..1   | display_name              |
| status                  |              | phone_number              |
| version                 |              | address_line              |
+-------------------------+              +---------------------------+

Java:
CustomerAccount {
    id, email, status, version,
    displayName, phoneNumber, addressLine
}
~~~

Điểm mấu chốt của quan hệ này là **cùng một identity**:

- `customer_account.id` là primary key của bảng chính.
- `customer_profile.account_id` vừa là primary key của bảng phụ, vừa là foreign key tham chiếu `customer_account.id`.
- Một hàng ở bảng chính tương ứng **tối đa một** hàng ở bảng phụ; mô hình có thể quy định **đúng một** hàng bảng phụ hoặc cho phép bảng phụ vắng mặt, tùy invariant và cấu hình.
- Trong ứng dụng, Hibernate biểu diễn hai hàng thuộc cùng một object `CustomerAccount`, không tạo thêm một entity `CustomerProfile` độc lập.

Trong mô hình này, `@SecondaryTable` phù hợp khi các nhóm cột có **cùng vòng đời và cùng danh tính nghiệp vụ**. Một bảng phụ không phải phương thức mặc định để giải quyết mọi quan hệ một-một; nếu hai đối tượng có nghiệp vụ/vòng đời riêng, ánh xạ `@OneToOne` thường hợp lý hơn.

### Động cơ thực tế

Các lý do thường gặp:

1. **Tương thích schema có sẵn:** dữ liệu một đối tượng vốn bị chia thành nhiều bảng; ứng dụng muốn làm việc qua một entity thống nhất.
2. **Tách nhóm cột ít truy cập:** hồ sơ mở rộng, cột kích thước lớn hoặc thông tin bổ sung không cần xuất hiện cùng nhóm cột chính trong schema.
3. **Quản trị schema:** các nhóm thuộc tính có chính sách truy cập, lịch sử phát triển hoặc ràng buộc khác nhau, nhưng vẫn thuộc một thực thể về mặt nghiệp vụ.
4. **Ánh xạ vertical partition theo thiết kế database:** giảm độ rộng hàng của bảng chính hoặc thuận tiện cho cấu trúc vật lý hiện hữu.

Không nên mặc định rằng tách bảng luôn giúp truy vấn nhanh hơn. Một entity thường vẫn cần JOIN hoặc truy vấn bổ sung để lấy dữ liệu ở bảng phụ. Hiệu quả phụ thuộc câu truy vấn, số dòng, index, kiểu cột và cách Hibernate load entity.

## 2. `@SecondaryTable` khác gì với `@OneToOne` và kế thừa?

Ba kỹ thuật có thể tạo ra nhiều bảng nhưng diễn đạt những ý nghĩa khác nhau:

| Kỹ thuật | Mô hình Java | Mô hình database | Khi dùng |
|---|---|---|---|
| `@SecondaryTable` | **Một entity** có field nằm ở nhiều bảng | Các bảng dùng chung primary key/identity của entity | Cột thuộc cùng thực thể và cùng lifecycle. |
| `@OneToOne` | **Hai entity** liên kết với nhau | Có thể dùng shared PK hoặc FK unique | Hai đối tượng có identity/vòng đời riêng; cần navigation, cascade hoặc repository riêng. |
| `@Inheritance(strategy = JOINED)` | Nhiều lớp entity trong một cây kế thừa | Bảng cha và bảng con theo phân cấp kiểu thực thể | Phân biệt các subtype có thuộc tính chuyên biệt. |

Ví dụ, nếu `CustomerProfile` phải được tạo, khóa/mở, xóa hoặc phân quyền độc lập với `CustomerAccount`, ánh xạ `@OneToOne` có thể diễn tả domain tốt hơn. Nếu `CustomerAccount` luôn bao gồm thuộc tính `displayName` và `addressLine`, chỉ do database tách lưu trữ, `@SecondaryTable` giúp object model đơn giản hơn.

`@MappedSuperclass` và `@Embeddable` cũng không đồng nghĩa bảng phụ:

- `@MappedSuperclass` cho phép lớp con thừa hưởng mapping, bản thân superclass không là một entity và không tự tạo bảng riêng theo cơ chế joined inheritance.
- `@Embeddable` nhóm các thuộc tính thành value object; mặc định các cột của nó nằm trong bảng của entity chứa, trừ khi sử dụng cơ chế override để chuyển cột sang bảng phụ.
- `@ElementCollection` thường mô hình hóa collection của value object ở bảng collection riêng; không phải “một bảng phụ chứa các cột của cùng một entity”.

## 3. Schema chuẩn: primary key ở bảng phụ đồng thời là foreign key

Sử dụng PostgreSQL, có thể tạo bảng và sequence phục vụ một entity:

~~~sql
CREATE SEQUENCE customer_account_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE customer_account (
    id       BIGINT       PRIMARY KEY,
    email    VARCHAR(200) NOT NULL UNIQUE,
    status   VARCHAR(20)  NOT NULL,
    version  BIGINT       NOT NULL
);

CREATE TABLE customer_profile (
    account_id    BIGINT       PRIMARY KEY,
    display_name  VARCHAR(120),
    phone_number  VARCHAR(30),
    address_line  VARCHAR(300),
    CONSTRAINT fk_customer_profile_account
        FOREIGN KEY (account_id)
        REFERENCES customer_account(id)
);
~~~

Ở đây, `customer_profile.account_id` không phải một ID được sinh độc lập. Nó **nhận cùng giá trị** với `customer_account.id`. Bởi vì `account_id` là primary key của bảng phụ nên không thể có hai hồ sơ khác nhau cho cùng một tài khoản.

Ví dụ dữ liệu:

~~~sql
INSERT INTO customer_account(id, email, status, version)
VALUES (1001, 'lan@example.com', 'ACTIVE', 0);

INSERT INTO customer_profile(
    account_id, display_name, phone_number, address_line
) VALUES (
    1001, 'Lan', '0900000000', 'District 1'
);
~~~

Hai hàng đều thuộc về account ID `1001`; trong Java chúng được nạp vào cùng một `CustomerAccount`.

### Vì sao khóa ở bảng phụ nên là PK + FK?

Nếu bảng phụ chỉ có cột `account_id` nhưng không unique/primary key, database có thể chứa nhiều hàng cho một account. Hibernate trong mapping secondary table mong đợi các thuộc tính bảng phụ quy về **một hàng của cùng entity**; dữ liệu nhiều hàng vi phạm giả định đó và có thể làm các phép join/loading trả kết quả sai hoặc bất thường.

Foreign key đảm bảo hàng ở bảng phụ không tham chiếu account không tồn tại. Primary key hoặc unique constraint đảm bảo mỗi account có tối đa một hàng phụ. Dù ORM có thể sinh schema trong môi trường thử nghiệm, production nên quản lý khóa/index/constraint bằng migration rõ ràng, thay vì chỉ tin vào annotation.

## 4. Ánh xạ entity bằng `@SecondaryTable` và `@Column(table = ...)`

Đây là ví dụ Jakarta Persistence đầy đủ về mapping cột:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.SecondaryTable;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customer_account")
@SecondaryTable(
    name = "customer_profile",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id",          // PK ở bảng phụ
        referencedColumnName = "id"   // PK ở bảng chính
    )
)
public class CustomerAccount {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "customer_account_gen"
    )
    @SequenceGenerator(
        name = "customer_account_gen",
        sequenceName = "customer_account_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "email", nullable = false, length = 200)
    private String email;                 // customer_account.email

    @Column(name = "status", nullable = false, length = 20)
    private String status;                // customer_account.status

    @Version
    @Column(name = "version", nullable = false)
    private long version;                 // customer_account.version

    @Column(
        name = "display_name",
        table = "customer_profile",
        length = 120
    )
    private String displayName;           // customer_profile.display_name

    @Column(
        name = "phone_number",
        table = "customer_profile",
        length = 30
    )
    private String phoneNumber;           // customer_profile.phone_number

    @Column(
        name = "address_line",
        table = "customer_profile",
        length = 300
    )
    private String addressLine;           // customer_profile.address_line

    protected CustomerAccount() {}        // JPA constructor

    public CustomerAccount(String email) {
        this.email = email;
        this.status = "ACTIVE";
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }

    public void updateProfile(
            String displayName, String phoneNumber, String addressLine) {
        this.displayName = displayName;
        this.phoneNumber = phoneNumber;
        this.addressLine = addressLine;
    }

    public void changeStatus(String status) {
        this.status = status;
    }
}
~~~

Các annotation có vai trò khác nhau:

| Annotation | Ý nghĩa |
|---|---|
| `@Table(name = "customer_account")` | Chỉ định bảng **chính** của entity. |
| `@SecondaryTable(name = "customer_profile")` | Khai báo một bảng **phụ** lưu thêm cột của cùng entity. |
| `@PrimaryKeyJoinColumn` trong `pkJoinColumns` | Chỉ rõ bảng phụ nối vào bảng chính bằng cột PK nào. |
| `@Column(table = "customer_profile")` | Chỉ định cột của một field nằm trong bảng phụ đã khai báo. |
| `@Column` không có `table` | Thường ánh xạ vào bảng chính. |
| `@Id` / `@GeneratedValue` | Định danh **một entity**; bảng phụ dùng lại cùng ID, không có generator riêng. |
| `@Version` | Cung cấp optimistic locking theo phạm vi entity, tránh mất cập nhật khi nhiều transaction cùng sửa dữ liệu. |

**Quy tắc cốt lõi:** `@SecondaryTable` chỉ khai báo **bảng**, còn `@Column(table = "...")` phân phối **thuộc tính** vào bảng đó. Nếu quên `table` trên `displayName`, Hibernate sẽ hiểu đó là cột `display_name` ở bảng chính theo mapping mặc định, rồi sinh SQL hoặc schema sai so với thiết kế.

Tên trong `@Column(table = "...")` phải tham chiếu đúng **tên bảng phụ trong annotation**, không phải tên trường Java hay tên cột khóa ngoại. Nếu bảng nằm ở schema khác, phần `schema`/`catalog` của `@SecondaryTable` nên được khai báo rõ theo database và naming strategy được sử dụng.

### Mặc định khi không khai báo `pkJoinColumns`

Với trường hợp PK đơn và cùng tên, JPA có thể suy ra cột khóa chính cần nối. Tuy nhiên, khi tên cột khác nhau hoặc schema cũ có quy ước riêng, khai báo `pkJoinColumns` tường minh giúp người đọc hiểu liên kết và tránh nhầm lẫn. Đối với composite key, cần khai báo đầy đủ từng thành phần khóa.

## 5. Hibernate tạo và đọc SQL ra sao?

Với entity `CustomerAccount`, code ứng dụng không cần biết `customer_profile` khi làm việc:

~~~java
CustomerAccount account = entityManager.find(CustomerAccount.class, 1001L);

System.out.println(account.getEmail());
System.out.println(account.getDisplayName());
~~~

Về mặt khái niệm, Hibernate cần kết hợp hai bảng theo khóa:

~~~sql
SELECT
    a.id,
    a.email,
    a.status,
    a.version,
    p.display_name,
    p.phone_number,
    p.address_line
FROM customer_account a
LEFT JOIN customer_profile p ON p.account_id = a.id
WHERE a.id = ?;
~~~

Đây là **SQL minh họa** để đọc dễ hiểu, không phải câu SQL Hibernate bắt buộc phải phát ra y hệt. Tùy mapping, cấu hình, optionality, bytecode enhancement, fetch plan và phiên bản, Hibernate có thể chọn dạng JOIN khác hoặc thêm truy vấn để tải cột bảng phụ. Một số mapping được thiết kế với invariant “luôn có hàng phụ” có thể sử dụng cách join khác so với bảng phụ tùy chọn.

Sau khi nạp dữ liệu, object Java vẫn có **một ID**:

~~~text
customer_account.id = 1001
customer_profile.account_id = 1001
          |
          v
CustomerAccount{id=1001, email=..., displayName=...}
~~~

Hibernate không trả về một `CustomerProfile` riêng do `@SecondaryTable`; mọi field bảng phụ được lắp vào state của `CustomerAccount`.

### HQL/JPQL vẫn viết theo field của entity

~~~java
List<CustomerAccount> accounts = entityManager.createQuery(
    """
    select a
    from CustomerAccount a
    where a.displayName like :prefix
    order by a.email
    """,
    CustomerAccount.class
).setParameter("prefix", "L%")
 .getResultList();
~~~

Không cần viết `join a.profile` trong JPQL, bởi entity không có association `profile`. Hibernate nhìn vào mapping của `displayName` để biết điều kiện tìm kiếm liên quan đến bảng phụ, sau đó phát sinh SQL thích hợp.

Một query projection cũng có thể lấy field thuộc nhiều bảng:

~~~java
List<Object[]> results = entityManager.createQuery(
    "select a.email, a.displayName from CustomerAccount a",
    Object[].class
).getResultList();
~~~

Khả năng lấy ít cột hơn hữu ích khi UI chỉ cần email và tên hiển thị; tránh phụ thuộc vào việc load đầy đủ một entity với nhiều field.

## 6. Thêm một entity: một lời gọi `persist()`, nhiều câu `INSERT`

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

CustomerAccount account = new CustomerAccount("new@example.com");
account.updateProfile("Mai", "0912345678", "Hanoi");
entityManager.persist(account);

tx.commit();
~~~

Một phiên thực thi với `GenerationType.SEQUENCE` có thể gồm:

~~~sql
-- Hibernate lấy ID trước nếu sequence/optimizer yêu cầu:
SELECT nextval('customer_account_seq');

-- Khi đồng bộ các thay đổi:
INSERT INTO customer_account (email, status, version, id)
VALUES (?, ?, ?, ?);

INSERT INTO customer_profile (
    display_name, phone_number, address_line, account_id
) VALUES (?, ?, ?, ?);

-- Transaction manager sau đó xác nhận commit.
~~~

Ví dụ bind:

~~~text
customer_account: ('new@example.com', 'ACTIVE', 0, 1002)
customer_profile: ('Mai', '0912345678', 'Hanoi', 1002)
~~~

Hai `INSERT` sử dụng cùng identifier. Trong schema có FK từ bảng phụ đến bảng chính, Hibernate phải phối hợp việc ghi để không vi phạm constraint; thứ tự SQL cụ thể vẫn thuộc cơ chế flush/mutation của provider. Nếu bước chèn bảng phụ thất bại, transaction cần rollback toàn bộ để không để lại dữ liệu dở dang ở bảng chính.

**Không nhầm lẫn `persist()` với một câu `INSERT`.** Trong Java bạn chỉ gọi một thao tác cho một entity, nhưng mapping yêu cầu Hibernate quản lý hai bảng. Một entity dùng ba bảng có thể phát sinh ba lệnh chèn; thêm các relationship và callback còn có thể tạo những SQL khác.

### Flush và commit là hai ranh giới

~~~java
entityManager.persist(account); // đăng ký trạng thái mới
entityManager.flush();          // có thể gửi cả hai INSERT xuống DB
// transaction vẫn có thể rollback tại đây
tx.commit();                    // xác nhận giao dịch
~~~

Nếu lỗi xảy ra sau `flush()` mà transaction rollback thành công, cả hai thao tác insert sẽ bị hủy. Bảng phụ không tạo một transaction độc lập; đó là một phần của cùng đơn vị công việc ORM.

## 7. Cập nhật field ở bảng chính hoặc bảng phụ

Hibernate dựa vào trạng thái entity managed và dirty checking để biết có thay đổi cần đồng bộ:

~~~java
tx.begin();
CustomerAccount account =
    entityManager.find(CustomerAccount.class, accountId);

account.updateProfile("Mai Nguyen", "0987654321", "Da Nang");
tx.commit();
~~~

Với mapping trên, một SQL cập nhật bảng phụ có thể là:

~~~sql
UPDATE customer_profile
SET display_name = ?,
    phone_number = ?,
    address_line = ?
WHERE account_id = ?;
~~~

Nếu thay đổi `status`, SQL ghi bảng chính có thể được phát sinh:

~~~sql
UPDATE customer_account
SET status = ?, version = ?
WHERE id = ? AND version = ?;
~~~

**Đây là các ví dụ về ý nghĩa SQL**, không phải bảo đảm Hibernate luôn phát sinh đúng số câu SQL hoặc chỉ các cột dirty. SQL thật còn tùy `@DynamicUpdate`, optimistic locking, generated values, mapping của từng bảng và cách Hibernate quản lý update across secondary tables.

### `@Version` có ích gì khi một entity trải trên nhiều bảng?

Một tài khoản có thông tin nằm ở hai bảng vẫn nên có **một cơ chế kiểm soát cập nhật đồng thời** ở cấp entity. Khi `@Version` được đặt trên thuộc tính mapped ở bảng chính như ví dụ, Hibernate có thể sử dụng version của entity để phát hiện transaction khác đã thay đổi entity. Một thay đổi ở bảng phụ có thể kéo theo xử lý tăng/check version và có SQL trên bảng chính tùy mapping, vì vậy đừng kết luận rằng sửa duy nhất một field ở bảng phụ sẽ *chắc chắn* chỉ có một câu `UPDATE customer_profile`.

Khi có cập nhật cạnh tranh, kiểm tra optimistic locking thông qua version giúp ngăn silent lost update theo semantics của provider. Tất cả thao tác ghi vào những bảng liên quan nên được thực hiện trong **transaction** rõ ràng; không chia một business operation thành hai commit chỉ vì nó tác động vào hai bảng.

### `@DynamicUpdate` và việc chọn cột

~~~java
@org.hibernate.annotations.DynamicUpdate
@Entity
@Table(name = "customer_account")
@SecondaryTable(name = "customer_profile", pkJoinColumns =
    @PrimaryKeyJoinColumn(name = "account_id", referencedColumnName = "id"))
class CustomerAccountDynamic {
    // Các field và getter tương tự ví dụ trên.
}
~~~

`@DynamicUpdate` là annotation riêng của Hibernate để tạo SQL update theo các cột thay đổi được phát hiện. Nó có thể hữu ích khi entity có nhiều cột nhưng mỗi lần chỉ sửa vài cột. Đổi lại, các tập cột dirty khác nhau làm SQL shape thay đổi, có thể làm giảm khả năng tái sử dụng statement và JDBC batching. Không mặc định dùng annotation này cho mọi entity có bảng phụ: cần quan sát SQL và đo theo workload thực tế.

## 8. Xóa entity và thứ tự xóa hai bảng

~~~java
tx.begin();
CustomerAccount account =
    entityManager.find(CustomerAccount.class, accountId);
entityManager.remove(account);
tx.commit();
~~~

Với foreign key từ bảng phụ tới bảng chính và không sử dụng `ON DELETE CASCADE`, database thường cần xóa hàng bảng phụ trước:

~~~sql
DELETE FROM customer_profile WHERE account_id = ?;
DELETE FROM customer_account WHERE id = ? AND version = ?;
~~~

Một số hệ thống có thể cấu hình xóa cascade tại database hoặc các cơ chế mutation đặc biệt. Dù SQL phát sinh ra sao, **bản ghi ở các bảng trong mapping thuộc về cùng một entity** và thao tác xóa entity phải duy trì các ràng buộc quan hệ trong transaction.

Nếu một thao tác `DELETE` thất bại vì khóa ngoại từ bảng khác tham chiếu đến account, không nên cố tiếp tục commit các thay đổi còn lại như không có chuyện gì xảy ra. Rollback transaction, đóng persistence context/session bị lỗi và xử lý nguyên nhân schema/nghiệp vụ.

### Từ phía code Java, không có `remove(profile)`

Ví dụ `@SecondaryTable` không có entity `CustomerProfile` nên không thể gọi `entityManager.remove(profile)` riêng. Nếu bảng phụ cần thao tác độc lập, lifecycle riêng hoặc được tham chiếu bởi các entity khác, việc mô hình hóa bằng `@OneToOne` hoặc entity riêng có thể là lựa chọn đúng đắn.

## 9. Bảng phụ bắt buộc và bảng phụ có thể thiếu hàng

Đây là một trong những quyết định quan trọng nhất khi dùng `@SecondaryTable`. Có hai mô hình dữ liệu:

**Mô hình A – Mỗi account luôn có hàng profile.**

~~~text
customer_account (id=1001)   <-->   customer_profile (account_id=1001)
customer_account (id=1002)   <-->   customer_profile (account_id=1002)
~~~

Ứng dụng duy trì invariant rằng mọi account đều có row ở bảng phụ. Có thể có cột nullable trong profile, nhưng row vẫn tồn tại. Điều này giúp update/delete rõ ràng hơn. Cần lưu ý rằng **FK từ bảng phụ tới bảng chính chỉ đảm bảo “profile có account”**, không tự đảm bảo “account phải có profile”. Nếu invariant là bắt buộc, cần bảo vệ ở luồng tạo dữ liệu, migration, kiểm thử và (nếu thiết kế hỗ trợ) cơ chế kiểm soát bổ sung tại DB.

**Mô hình B – Profile thật sự tùy chọn.**

~~~text
customer_account (id=1001)   <-->   customer_profile (account_id=1001)
customer_account (id=1002)   <-->   [chưa có profile row]
~~~

Mô hình này xuất hiện khi người dùng được phép tạo account trước rồi bổ sung hồ sơ sau. Khi đọc, database cần xử lý trường hợp không có hàng phụ (thường thông qua outer join hoặc cách tải tương đương); khi cập nhật, ORM cần biết khi nào phải **thêm hàng bảng phụ** thay vì update một hàng chưa tồn tại.

### Không nhầm `nullable` với “bảng phụ tùy chọn”

~~~java
@Column(name = "phone_number", table = "customer_profile", nullable = true)
private String phoneNumber;
~~~

`nullable = true` mô tả khả năng cột `phone_number` chứa SQL `NULL`. Nó **không tự định nghĩa** liệu hàng `customer_profile` có thể không tồn tại hay Hibernate sẽ phải chèn hàng đó khi một field khác được đặt sau này.

Hibernate có các cấu hình mở rộng theo phiên bản liên quan bảng phụ tùy chọn. Với các dòng Hibernate 6.x hỗ trợ annotation `org.hibernate.annotations.SecondaryRow`, có thể chỉ rõ ý định bảng phụ optional bằng cú pháp dạng:

~~~java
@Entity
@Table(name = "customer_account")
@SecondaryTable(
    name = "customer_profile",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id", referencedColumnName = "id"
    )
)
@org.hibernate.annotations.SecondaryRow(
    table = "customer_profile",
    optional = true
)
class OptionalCustomerAccount {
    @Id
    Long id;

    @Column(name = "display_name", table = "customer_profile")
    String displayName;
}
~~~

Đây là **mở rộng Hibernate, không thuộc JPA chuẩn**. Cần đối chiếu API của đúng phiên bản Hibernate đang chạy; có phiên bản/kiểu mapping có quy tắc insert/update và fetch riêng đối với optional secondary rows. Cách ứng dụng phát hiện row vắng mặt, tạo mới khi thay đổi field và xử lý những giá trị `NULL` cần được kiểm chứng với schema thật.

**Một quyết định thiết kế hữu ích:** nếu row profile có lifecycle độc lập rõ ràng (có thể tạo sau, xóa riêng, có trạng thái nghiệp vụ riêng) và ứng dụng phải xử lý nhiều quy tắc tùy chọn, `@OneToOne(optional = true)` với entity `CustomerProfile` có thể diễn đạt domain minh bạch hơn. Bảng phụ phù hợp nhất khi row phụ được quản lý như **phần lưu trữ của cùng một entity**.

## 10. Nhiều hơn một bảng phụ với `@SecondaryTables`

Giả sử account có thêm bảng `customer_preferences` lưu timezone, ngôn ngữ và định dạng giao diện. Database có thể gồm:

~~~sql
CREATE TABLE customer_preferences (
    account_id   BIGINT PRIMARY KEY,
    language_tag VARCHAR(20),
    timezone     VARCHAR(80),
    CONSTRAINT fk_preferences_account
        FOREIGN KEY (account_id)
        REFERENCES customer_account(id)
);
~~~

Entity có thể ánh xạ đồng thời ba bảng:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customer_account")
@SecondaryTables({
    @SecondaryTable(
        name = "customer_profile",
        pkJoinColumns = @PrimaryKeyJoinColumn(
            name = "account_id",
            referencedColumnName = "id"
        )
    ),
    @SecondaryTable(
        name = "customer_preferences",
        pkJoinColumns = @PrimaryKeyJoinColumn(
            name = "account_id",
            referencedColumnName = "id"
        )
    )
})
public class CustomerAccountWithPreferences {
    @Id
    private Long id;

    @Column(name = "email", table = "customer_account")
    private String email;

    @Column(name = "display_name", table = "customer_profile")
    private String displayName;

    @Column(name = "language_tag", table = "customer_preferences")
    private String languageTag;

    @Column(name = "timezone", table = "customer_preferences")
    private String timezone;
}
~~~

Trong code này, `@SecondaryTables` chỉ là container chứa nhiều `@SecondaryTable`; mỗi field chỉ rõ bảng tương ứng. Có thể thêm constructor/getter và generator tùy ứng dụng. Nếu dùng schema thật ở phần trước, cần chú ý trường `status` và `version` bắt buộc của bảng chính: ví dụ bổ sung trên **chỉ minh họa mapping nhiều bảng**, không phải replacement hoàn chỉnh cho class `CustomerAccount` với đầy đủ constraint.

Khi một entity có ba bảng, việc insert, update, delete có thể tác động vào cả ba. Mức độ phức tạp SQL, số round trip JDBC và các tình huống thiếu row tăng theo số bảng phụ, nên hãy cân nhắc lợi ích thiết kế trước khi thêm quá nhiều `@SecondaryTable`.

## 11. Khóa chính ghép: mỗi cột của khóa phải được nối đúng

Nếu entity được định danh bằng cặp `(tenant_id, account_no)`, bảng phụ cần dùng lại **toàn bộ** cặp khóa đó:

~~~sql
CREATE TABLE tenant_account (
    tenant_id  BIGINT NOT NULL,
    account_no BIGINT NOT NULL,
    email      VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, account_no)
);

CREATE TABLE tenant_account_profile (
    tenant_id    BIGINT NOT NULL,
    account_no   BIGINT NOT NULL,
    display_name VARCHAR(120),
    PRIMARY KEY (tenant_id, account_no),
    FOREIGN KEY (tenant_id, account_no)
        REFERENCES tenant_account(tenant_id, account_no)
);
~~~

Trong Java, `@EmbeddedId` mô tả định danh ghép; secondary table phải tham chiếu đủ cả hai cột:

~~~java
import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class TenantAccountId implements Serializable {
    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "account_no")
    private Long accountNo;

    protected TenantAccountId() {}

    public TenantAccountId(Long tenantId, Long accountNo) {
        this.tenantId = tenantId;
        this.accountNo = accountNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TenantAccountId that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(accountNo, that.accountNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, accountNo);
    }
}

@Entity
@Table(name = "tenant_account")
@SecondaryTable(
    name = "tenant_account_profile",
    pkJoinColumns = {
        @PrimaryKeyJoinColumn(
            name = "tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @PrimaryKeyJoinColumn(
            name = "account_no",
            referencedColumnName = "account_no"
        )
    }
)
public class TenantAccount {
    @EmbeddedId
    private TenantAccountId id;

    @Column(name = "email")
    private String email;

    @Column(name = "display_name", table = "tenant_account_profile")
    private String displayName;

    protected TenantAccount() {}

    // constructor, getter, domain methods ...
}
~~~

Với composite key, một lỗi rất dễ mắc là chỉ khai báo một cột join hoặc tham chiếu nhầm tên cột. Khi đó SQL join có thể nhận nhiều hàng hoặc không tìm đúng row. `equals()` và `hashCode()` trong ID class cũng quan trọng để JPA/Hibernate và collection Java xác định identity đúng; không nên xem chúng là chi tiết bỏ qua được.

## 12. Embeddable chứa các thuộc tính nằm trong bảng phụ

Trong domain model, nhóm thuộc tính hồ sơ có thể đóng gói thành một value object thay vì ba field rời:

~~~java
@Embeddable
public class ContactInfo {
    private String phoneNumber;
    private String addressLine;

    protected ContactInfo() {}

    public ContactInfo(String phoneNumber, String addressLine) {
        this.phoneNumber = phoneNumber;
        this.addressLine = addressLine;
    }
}
~~~

Để chuyển các field bên trong `@Embedded` sang bảng phụ, dùng `@AttributeOverrides` kèm `@Column(table = ...)`:

~~~java
@Entity
@Table(name = "customer_account")
@SecondaryTable(
    name = "customer_profile",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id", referencedColumnName = "id"
    )
)
public class CustomerAccountWithContact {
    @Id
    private Long id;

    @Column(name = "email")
    private String email;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "phoneNumber",
            column = @Column(
                name = "phone_number",
                table = "customer_profile",
                length = 30
            )
        ),
        @AttributeOverride(
            name = "addressLine",
            column = @Column(
                name = "address_line",
                table = "customer_profile",
                length = 300
            )
        )
    })
    private ContactInfo contactInfo;

    protected CustomerAccountWithContact() {}
}
~~~

`ContactInfo` ở ví dụ này **không phải entity độc lập**; nó không có `@Id` hay repository riêng. Hibernate ánh xạ từng field của value object vào các cột `customer_profile`, còn identity của hàng vẫn là `CustomerAccountWithContact.id`.

Chú ý: nếu database yêu cầu một hàng bảng phụ tồn tại kể cả khi toàn bộ field ContactInfo đều null, hành vi insert optional row phải được thiết kế và kiểm chứng. Việc tạo hoặc không tạo Java `ContactInfo` không tự định nghĩa một row tồn tại hay không trong schema.

## 13. Schema, catalog và constraint trên bảng phụ

Annotation `@SecondaryTable` có thể chỉ rõ schema:

~~~java
@Entity
@Table(name = "customer_account", schema = "core")
@SecondaryTable(
    name = "customer_profile",
    schema = "detail",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id", referencedColumnName = "id"
    ),
    foreignKey = @ForeignKey(name = "fk_customer_profile_account")
)
public class CustomerAccountAcrossSchemas {
    @Id
    private Long id;

    @Column(name = "email")
    private String email;

    @Column(name = "display_name", table = "customer_profile")
    private String displayName;
}
~~~

Đây là schema mapping minh họa; việc có thể tạo foreign key giữa hai schema, cấp quyền truy cập và cách quote identifier phụ thuộc DBMS. Trong production, migration tool như Flyway/Liquibase thường tạo database objects; annotation có thể là nguồn mô tả mapping và một phần metadata schema generation, nhưng không thay thế việc kiểm soát DDL trên môi trường thật.

### Unique constraint và index

`@SecondaryTable` có thuộc tính metadata schema như `uniqueConstraints` và `indexes` trong các phiên bản JPA hỗ trợ:

~~~java
@SecondaryTable(
    name = "customer_profile",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "account_id", referencedColumnName = "id"
    ),
    indexes = {
        @Index(name = "ix_customer_profile_display_name",
               columnList = "display_name")
    }
)
~~~

Index theo `display_name` có thể hỗ trợ các truy vấn thực sự lọc/sắp xếp theo cột đó, nhưng lợi ích phụ thuộc selectivity và plan của DB. Bởi `account_id` đã là primary key, DB thông thường có index trên khóa này; không nên tự động thêm index trùng lặp vô ích.

Khóa ngoại liên kết bảng phụ với bảng chính nên được quản lý đúng ở **database level**. Đừng nhầm `@ForeignKey` với cơ chế runtime cascade của JPA: `@ForeignKey` chủ yếu mô tả constraint trong DDL; nó không làm Hibernate chuyển một bảng phụ thành entity có cascade độc lập.

## 14. Tác động tới hiệu năng đọc và ghi

### 14.1. Khi đọc: có thể cần join nhiều bảng

Nếu truy vấn trả entity và các thuộc tính bảng phụ được tải cùng, SQL có thể JOIN thêm bảng profile. Việc tách bảng đôi khi giúp bảng chính gọn hơn, nhưng cũng có thể tăng:

- chi phí join theo PK/FK;
- lượng dữ liệu đọc nếu fetch plan cần cột ở nhiều bảng;
- số SQL/round trip nếu bảng phụ được tải qua các select bổ sung;
- độ phức tạp execution plan khi kết hợp thêm association khác.

Hibernate không đảm bảo “field ở secondary table luôn lazy”. Với basic field, `@Basic(fetch = FetchType.LAZY)` là hint và việc lazy thật sự có thể cần **bytecode enhancement** hoặc cơ chế hỗ trợ của phiên bản/provider. Ngay cả khi không truy cập field trong code, câu SQL tải entity có thể đã đọc cột đó.

~~~java
@Basic(fetch = FetchType.LAZY)
@Column(name = "address_line", table = "customer_profile")
private String addressLine;
~~~

Annotation trên là một **ý định tải trễ**, không đủ để khẳng định mọi Hibernate setup sẽ bỏ cột này khỏi `SELECT` ban đầu. Muốn giảm dữ liệu đọc chắc chắn cho một endpoint chỉ cần email, dùng projection:

~~~java
List<String> emails = entityManager.createQuery(
    "select a.email from CustomerAccount a",
    String.class
).getResultList();
~~~

Khi đo hiệu năng, xem cả SQL log, execution plan, kích thước dữ liệu, thống kê cache và số round trip.

### 14.2. Khi ghi: một entity có thể tác động nhiều bảng

Việc `persist()` một entity ở hai bảng đòi hỏi tối thiểu một thao tác ghi cho mỗi row cần tạo; `remove()` phải xử lý các row thuộc entity. Với update, dirty checking và mapping quyết định bảng nào được ghi, nhưng optimistic locking có thể làm phát sinh thêm SQL tại bảng chính.

Không nên kỳ vọng JDBC batch tự động gom mọi lệnh insert thành một statement vì các bảng khác nhau có SQL shape khác nhau. `hibernate.jdbc.batch_size` và `hibernate.order_inserts` có thể giúp trong workload lớn, nhưng chia dữ liệu ra nhiều bảng cũng tạo thêm loại SQL cần thực thi.

### 14.3. Khi cache: entity vẫn là một đơn vị

First-level cache quản lý **entity identity**, không tạo hai entity riêng cho hai bảng. Nếu bật second-level cache cho entity, cách Hibernate lưu và vô hiệu hóa state phụ thuộc cấu hình cache/provider; không nên coi secondary table là một aggregate cache độc lập có thể refresh riêng như một entity `@OneToOne`. Bulk SQL hoặc công cụ bên ngoài sửa thẳng bảng phụ có thể khiến state/cache của entity bị cũ nếu ứng dụng không có chiến lược đồng bộ phù hợp.

## 15. Constraint, null và kiểm tra dữ liệu

### `@Column(nullable = false)` áp dụng lên cột nào?

~~~java
@Column(
    name = "display_name",
    table = "customer_profile",
    nullable = false
)
private String displayName;
~~~

Khai báo này mô tả `customer_profile.display_name` không được null khi hàng phụ tồn tại và schema được tạo/kiểm soát đúng. Nó **không bảo đảm tự thân** rằng mỗi hàng của `customer_account` đều có một hàng ở `customer_profile`. Đó là hai invariant khác nhau:

1. Một hàng profile không được có display name null.
2. Mỗi account bắt buộc có một hàng profile.

Cần thiết kế cả hai nếu nghiệp vụ yêu cầu. Tránh lưu thiếu row rồi dựa vào dữ liệu mặc định của Java để che đi sự không nhất quán của schema.

### Khi dữ liệu bị sửa bằng native SQL

Ví dụ một batch khác chạy:

~~~sql
DELETE FROM customer_profile WHERE account_id = 1001;
~~~

Nếu Hibernate đang giữ `CustomerAccount(1001)` managed với snapshot cũ, field Java có thể chưa tự phản ánh row mới bị xóa. Trong transaction/session mới, hành vi nạp entity phụ thuộc optional secondary row mapping. Hibernate không tự biết mọi câu SQL của ứng dụng khác đã làm gì; cần phối hợp cache invalidation, transaction isolation và refresh/reload khi cần.

### Nếu chèn bằng script migration

~~~sql
INSERT INTO customer_account(id, email, status, version)
VALUES (2001, 'migration@example.com', 'ACTIVE', 0);
-- Quên INSERT customer_profile cho account 2001.
~~~

Nếu mapping giả định hàng profile bắt buộc, entity có thể tải khác mong đợi hoặc update không có hàng tương ứng. Vì thế, script migration phải backfill hoặc định nghĩa rõ các row optional, đồng thời giữ toàn vẹn PK/FK. Một mapping đúng trong Java không thể sửa mọi dữ liệu nguồn đã sai quy tắc.

## 16. Transaction, flush và lỗi giữa các bảng

Một entity trải trên nhiều bảng phải được quản lý trong transaction phù hợp. Ví dụ:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();
try {
    CustomerAccount account =
        new CustomerAccount("atomic@example.com");
    account.updateProfile("Atomic", "0123456789", "Hue");
    entityManager.persist(account);

    entityManager.flush();
    // Nếu không có lỗi, các INSERT có thể đã chạy trong transaction.
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }
    throw failure;
}
~~~

Ví dụ trên dùng `EntityManager` application-managed với `RESOURCE_LOCAL`. Trong Spring/JTA, transaction manager sở hữu commit/rollback; không gọi `getTransaction()` ở một transaction-scoped `EntityManager` do container quản lý.

Những điều cần hiểu:

- Nếu insert bảng chính thành công nhưng insert bảng phụ vi phạm constraint, **rollback** transaction (nếu DB hỗ trợ transaction bình thường) sẽ hủy cả thay đổi ở bảng chính.
- Nếu `flush()` thành công nhưng sau đó code ném exception và rollback, dữ liệu vẫn không được commit.
- Nếu lỗi xảy ra ngay tại `commit()`, không nên giả định tuyệt đối database đã hoặc chưa commit khi client không nhận phản hồi; cần chiến lược xác minh/idempotency cho nghiệp vụ nhạy cảm.
- Sau JDBC/Hibernate exception ở flush, không nên tiếp tục ghi với cùng persistence context bị lỗi; rollback và kết thúc session/context theo ownership của ứng dụng.

### Optimistic locking không thay thế transaction

`@Version` giúp phát hiện cập nhật cạnh tranh ở mức entity, nhưng không làm các câu lệnh ở hai bảng tự trở thành một giao dịch nếu ứng dụng cố tình chia chúng thành hai commit. Atomicity đến từ transaction và database, còn version giúp kiểm soát xung đột cập nhật.

## 17. Tránh một số nhầm lẫn trong mapping

### 17.1. Chỉ khai báo `@SecondaryTable` mà quên `@Column(table = ...)`

~~~java
@SecondaryTable(name = "customer_profile")
@Entity
class WrongAccount {
    @Id Long id;

    @Column(name = "display_name") // thiếu table="customer_profile"
    String displayName;
}
~~~

Hibernate mặc định đặt `display_name` ở primary table. Nếu schema thật không có cột này, query có thể báo lỗi “column not found”; nếu bật schema generation không kiểm soát, nó có thể tạo cột ở bảng không mong muốn.

### 17.2. Đặt khóa phụ không trùng khóa chính

~~~text
customer_account.id = 25
customer_profile.profile_id = 999 (independent ID)
customer_profile.account_id = 25
~~~

Nếu bảng profile có identity độc lập, hãy cân nhắc entity riêng với `@OneToOne`. Với `@SecondaryTable`, hàng phụ phải dùng khóa nối đại diện cùng entity identity. Một schema profile có `profile_id` độc lập và `account_id` chỉ là FK thường không khớp trực tiếp ý nghĩa shared PK secondary table.

### 17.3. Tưởng một bảng phụ tương đương lazy association

`@SecondaryTable` không làm Hibernate tạo property kiểu `CustomerProfile` để tải lười riêng. Các cột phụ vẫn nằm trong mapping một entity. Muốn có fetch strategy độc lập cho profile entity, `@OneToOne` có thể diễn đạt nhu cầu rõ hơn.

### 17.4. Dùng `@OneToMany` khi muốn lưu field đơn

Bảng phụ của một entity là quan hệ 1:1 theo identity. `@OneToMany` biểu diễn nhiều row thuộc tập con; sử dụng nó chỉ để lưu phone/display name ở bảng khác khiến object model và lifecycle thay đổi không cần thiết.

### 17.5. Dựa vào JPA schema generation làm migration production

Annotation chỉ nói Hibernate cần map như thế nào; schema production vẫn phải được kiểm soát. Khi triển khai thay đổi, cần DDL, backfill, index, quyền truy cập và kế hoạch rollback migration. Đừng để `hbm2ddl.auto=update` âm thầm “chữa” schema đang chạy ở production mà không có review.

### 17.6. Đặt cùng tên cột ở hai bảng và bỏ chỉ định table

~~~text
customer_account.status
customer_profile.status
~~~

Nếu một entity có hai field cùng map tên cột `status` nhưng thuộc hai bảng khác nhau, `@Column(table = ...)` là cách phân biệt. Mọi trường hợp table không khớp metadata có thể dẫn tới ánh xạ nhầm hoặc boot-time validation error.

### 17.7. Tưởng cập nhật bảng phụ là thay đổi độc lập không cần version

Đối với object `CustomerAccount`, các field bảng chính và bảng phụ là state của **một managed entity**. Đọc/sửa chúng trong các transaction cạnh tranh cần được bảo vệ bởi isolation và optimistic/pessimistic locking tương ứng. Không nên chỉ kiểm tra version ở một phần và bỏ qua xung đột nghiệp vụ ở phần còn lại.

## 18. Chuyển từ một bảng sang nhiều bảng mà không mất dữ liệu

Một tình huống thực tế là bảng `customer_account` ban đầu chứa tất cả cột:

~~~sql
-- Schema cũ (minh họa):
customer_account(
  id, email, status, version,
  display_name, phone_number, address_line
)
~~~

Muốn tách nhóm profile, migration nên đi qua các bước có kiểm soát:

1. **Tạo bảng phụ** với `account_id` là PK + FK đến bảng chính. Chọn kiểu dữ liệu/nullable phù hợp.
2. **Backfill** dữ liệu từ cột cũ sang bảng phụ bằng SQL migration và kiểm tra số row/giá trị.
3. **Xác minh tính toàn vẹn**: không thiếu profile bắt buộc, không có duplicate ID, các FK hợp lệ và không bị mất giá trị null/chuỗi dài.
4. **Cập nhật mapping ứng dụng** để chuyển các field sang `@Column(table = "customer_profile")`. Với hệ thống không dừng ghi, phải có chiến lược dual-write, versioned deployment hoặc một giai đoạn đồng bộ thích hợp.
5. **Theo dõi SQL và lỗi** sau triển khai; kiểm tra tạo, sửa, xóa entity trong cả hai bảng.
6. **Xóa cột cũ** chỉ sau khi chắc chắn application và batch jobs không còn phụ thuộc, và đã có kế hoạch rollback.

Ví dụ backfill PostgreSQL:

~~~sql
INSERT INTO customer_profile (
    account_id, display_name, phone_number, address_line
)
SELECT id, display_name, phone_number, address_line
FROM customer_account;
~~~

Đây là mẫu cho migration một lần trên schema cũ, giả định bảng phụ mới chưa có row. Nếu cần chạy lại không lỗi, phải thiết kế idempotent migration theo DBMS, như `ON CONFLICT` trong PostgreSQL với quy tắc cập nhật cụ thể; không thực hiện blind insert trên production đã có dữ liệu.

### Điều gì khó nhất khi chuyển schema trong hệ thống đang chạy?

Rủi ro thường nằm ở **giai đoạn hai phiên bản ứng dụng cùng hoạt động**: code cũ tiếp tục ghi vào cột `display_name` bảng chính trong khi code mới đọc từ `customer_profile`. Nếu không có chiến lược chuyển đổi, dữ liệu có thể lệch dù mapping của từng phiên bản độc lập đều đúng. Cần phối hợp tiến trình ghi, backfill và thời điểm thay đổi quyền đọc.

## 19. Kiểm chứng mapping bằng thí nghiệm

Để quan sát Hibernate xử lý một entity trải trên nhiều bảng, bật logging SQL ở môi trường học tập:

~~~properties
# Ví dụ Spring Boot + Hibernate 6:
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger và cú pháp cấu hình có thể thay đổi theo phiên bản/framework. Log bind values có thể chứa dữ liệu cá nhân nên chỉ bật theo chính sách bảo mật phù hợp.

### Thí nghiệm A — Persist tạo hai hàng

~~~java
tx.begin();
CustomerAccount a = new CustomerAccount("test-a@example.com");
a.updateProfile("Test A", "0123", "HCM");
entityManager.persist(a);
tx.commit();
~~~

Xác minh bằng SQL:

~~~sql
SELECT a.id, a.email, p.display_name, p.phone_number
FROM customer_account a
JOIN customer_profile p ON p.account_id = a.id
WHERE a.email = 'test-a@example.com';
~~~

Kết quả kỳ vọng: một ID xuất hiện ở bảng chính và bảng phụ, và Hibernate trả về một `CustomerAccount`.

### Thí nghiệm B — Chỉ sửa field ở bảng phụ

~~~java
tx.begin();
CustomerAccount a =
    entityManager.find(CustomerAccount.class, accountId);
a.updateProfile("Test A Updated", "0456", "HCM");
tx.commit();
~~~

Xem log SQL để xác định các bảng Hibernate cập nhật. Nếu có `@Version`, lưu ý một lệnh update ở bảng chính có thể tham gia tăng/check version dù chỉ field của bảng phụ được sửa.

### Thí nghiệm C — Chỉ sửa field ở bảng chính

~~~java
tx.begin();
CustomerAccount a =
    entityManager.find(CustomerAccount.class, accountId);
a.changeStatus("SUSPENDED");
tx.commit();
~~~

Kiểm tra trạng thái trong `customer_account` và bảo đảm profile vẫn liên kết cùng ID.

### Thí nghiệm D — Xóa một entity

~~~java
tx.begin();
CustomerAccount a =
    entityManager.find(CustomerAccount.class, accountId);
entityManager.remove(a);
tx.commit();
~~~

Xác minh cả hai bảng không còn row tương ứng và không vi phạm FK. Quan sát thứ tự `DELETE` thực tế.

### Thí nghiệm E — Rollback

~~~java
tx.begin();
CustomerAccount a = new CustomerAccount("rollback@example.com");
a.updateProfile("Rollback", "000", "HCM");
entityManager.persist(a);
entityManager.flush();
tx.rollback();
~~~

Sau rollback, mở transaction mới và query từ DB; không còn row được commit ở bảng nào, miễn cả hai bảng tham gia cùng transaction DB bình thường. Một ID được cấp từ sequence trước rollback có thể bị bỏ trống trong dãy số; đó là hành vi khác với tính nguyên tử của hai `INSERT`.

### Thí nghiệm F — Bảng phụ thiếu row

Trong môi trường thử nghiệm, tạo một row bảng chính không có row profile, rồi:

1. Đọc entity và quan sát SQL/giá trị field phụ.
2. Thay đổi `displayName` và flush.
3. Xem ORM phát sinh `INSERT` hay `UPDATE` trên bảng phụ, và có lỗi affected rows hay không.
4. Lặp lại với cấu hình optional row mà phiên bản Hibernate đang sử dụng hỗ trợ.

Bài thực hành này làm rõ khác biệt giữa cột có thể null và **bản ghi bảng phụ thực sự không tồn tại**; đây không phải chi tiết nên đoán từ tên annotation.

## 20. Cách quyết định có nên dùng `@SecondaryTable`

Trước khi chọn mapping, hãy tự hỏi:

| Câu hỏi | Nếu câu trả lời là “có” |
|---|---|
| Các cột ở bảng phụ luôn thuộc về đúng cùng một business identity? | `@SecondaryTable` là ứng viên phù hợp. |
| Hàng bảng phụ có cùng vòng đời tạo, sửa, xóa với entity chính? | Mô hình một entity thường đơn giản. |
| Bảng phụ cần có ID và repository riêng, trạng thái riêng hoặc service riêng? | Cân nhắc `@OneToOne` thay vì `@SecondaryTable`. |
| Có nhiều row phụ cho một row chính? | Đây không còn là secondary table theo shared PK; xem `@OneToMany`/`@ElementCollection`. |
| Chủ yếu chỉ cần ít cột ở bảng chính? | Cân nhắc cả projection/fetch plan; secondary table không tự hứa hẹn giảm SQL đọc. |
| Có bảng phụ tùy chọn và nhiều trường hợp thiếu row? | Xác minh optional row support theo Hibernate version hoặc mô hình thành entity riêng. |
| Schema cũ bắt buộc tách cùng một entity qua nhiều bảng? | `@SecondaryTable` có thể giúp Java domain model thống nhất. |

### Mẫu tư duy để đọc mapping

Khi gặp một entity dùng `@SecondaryTable`, có thể lần theo thứ tự:

1. `@Table` nói **bảng chính** nào giữ ID.
2. `@SecondaryTable` nói **các bảng phụ** nào tham gia cùng entity.
3. `pkJoinColumns` nói **khóa của bảng phụ** tham chiếu khóa chính như thế nào.
4. `@Column(table = ...)` nói **mỗi field** được lưu ở bảng nào.
5. `@Version`, nullability, optional row, cascade database và transaction xác định **quy tắc cập nhật an toàn**.
6. SQL log và execution plan cho biết **chi phí thực tế** khi load và mutate entity.

Một entity ánh xạ qua nhiều bảng vẫn là **một thực thể trong persistence context**. Hibernate chịu trách nhiệm chuyển các thay đổi của object thành nhiều lệnh SQL đến các bảng liên quan, còn thiết kế PK/FK và transaction bảo đảm các hàng đó đại diện nhất quán cho cùng một bản ghi nghiệp vụ. Khi hiểu rõ ranh giới này, `@SecondaryTable` trở thành công cụ hữu ích để tích hợp schema quan hệ phức tạp mà không làm object model rời rạc.
