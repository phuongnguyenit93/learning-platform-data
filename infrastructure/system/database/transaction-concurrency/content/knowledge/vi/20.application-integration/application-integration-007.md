# Bộ nhớ đối tượng của ORM và dữ liệu đã thay đổi ở giao dịch khác

ORM (Object-Relational Mapping) ánh xạ hàng trong cơ sở dữ liệu thành đối tượng trong bộ nhớ ứng dụng. Khi một đối tượng đã được ORM nạp vào session hoặc persistence context, ORM thường giữ một bản đại diện của nó để theo dõi thay đổi và bảo đảm cùng một hàng không bị biểu diễn thành nhiều đối tượng đang được quản lý trong cùng phạm vi làm việc.

Điều này tạo ra một tình huống dễ gây nhầm lẫn: một transaction khác có thể cập nhật và commit hàng trong database, nhưng đối tượng mà ứng dụng đang giữ vẫn chứa giá trị cũ. Database đã có dữ liệu mới, còn object trong bộ nhớ vẫn phản ánh lần đọc trước. Đây là **stale object state** (trạng thái đối tượng lỗi thời).

Vấn đề không nhất thiết có nghĩa ORM đọc sai hoặc database không cập nhật. ORM có thể đang trả lại đối tượng đã được quản lý trong identity map thay vì tải lại và ghi đè trạng thái của nó. Muốn lấy dữ liệu mới, ứng dụng cần chọn đúng thao tác như `refresh`, `expire`, `clear`/`detach`, hoặc bắt đầu một transaction mới tùy ORM và isolation level.

Ngoài việc hiển thị giá trị cũ, object lỗi thời còn có thể gây lost update: ứng dụng sửa object dựa trên dữ liệu cũ rồi ghi lại, vô tình ghi đè thay đổi đã commit từ transaction khác. Cần kết hợp vòng đời persistence context với optimistic locking, pessimistic locking và quy tắc isolation của database.

## 1. Vì sao ORM giữ đối tượng trong bộ nhớ?

Khi ứng dụng truy vấn một hàng `Account`, ORM thường tạo một object và đưa nó vào một vùng quản lý như Hibernate persistence context, JPA `EntityManager`, SQLAlchemy `Session` hoặc EF Core `DbContext`.

Vùng quản lý này có một số nhiệm vụ:

- **Identity map:** với cùng một khóa chính trong cùng persistence context, ORM thường trả về cùng một instance object.
- **Dirty checking:** ORM theo dõi trạng thái để biết object nào đã thay đổi và cần phát sinh `UPDATE`.
- **Unit of work:** ORM gom các thay đổi rồi đồng bộ chúng với database khi flush hoặc commit.
- **Quản lý quan hệ:** ORM theo dõi association giữa các object và điều phối insert/update/delete theo thứ tự phù hợp.
- **Tối ưu truy cập:** ORM có thể tránh truy vấn lại một hàng đã được nạp trong cùng context.

Ví dụ, ứng dụng đọc tài khoản 42:

```java
Account account = entityManager.find(Account.class, 42L);
System.out.println(account.getBalance());
```

Sau lần đọc đầu, `account` trở thành managed entity trong persistence context. Nếu cùng `EntityManager` gọi `find` lại với khóa 42, JPA thường trả về instance đang được quản lý. ORM không nhất thiết gửi một `SELECT` mới để lấy dữ liệu hiện tại từ database.

Đây là hành vi có chủ đích. Nếu mỗi lần truy cập đều tạo object mới và thay thế object cũ, ORM sẽ khó theo dõi dirty state, quan hệ giữa object và các thay đổi chưa flush của ứng dụng.

## 2. Identity map và stale object state

Identity map là bản đồ nội bộ ánh xạ khóa định danh của hàng sang object đang được quản lý. Ví dụ:

```text
Persistence context của ứng dụng A

Entity key             Object trong bộ nhớ
Account#42       --->  Account(id=42, balance=100)
Account#77       --->  Account(id=77, balance=250)
```

Giả sử transaction T1 của ứng dụng A đã nạp `Account#42` với `balance = 100`. Transaction T2 của một request khác cập nhật số dư thành 120 rồi commit. Database hiện có 120, nhưng identity map của A vẫn đang trỏ đến object chứa 100.

```text
Database sau khi T2 commit:
  Account#42.balance = 120

Persistence context của A:
  Account#42.balance = 100  [object đã nạp trước đó]
```

Nếu A gọi `find(Account.class, 42L)` lần nữa trong cùng context, ORM có thể trả lại object cũ với balance 100. Đây là lý do một truy vấn theo khóa chính không nhất thiết đồng nghĩa với việc đọc lại dữ liệu mới nhất từ database.

### 2.1. Cùng một object trong một context không có nghĩa là cùng một snapshot database

Identity map là cơ chế ở tầng ORM. Snapshot/isolation là cơ chế ở tầng database. Hai lớp này hoạt động độc lập nhưng ảnh hưởng lẫn nhau.

- Identity map quyết định ORM có dùng lại instance đã nạp hay không.
- Isolation level quyết định transaction có thể nhìn thấy những commit nào từ transaction khác.
- Cache cấp hai hoặc query cache có thể thêm một lớp lưu dữ liệu giữa ORM và database.

Ngay cả khi isolation level cho phép câu `SELECT` mới nhìn thấy commit mới, ORM vẫn có thể trả lại object managed đang giữ giá trị cũ. Ngược lại, nếu transaction đang dùng snapshot cố định, thao tác refresh có thể truy vấn database nhưng vẫn chỉ nhìn thấy phiên bản theo snapshot cũ.

Vì vậy, muốn hiểu vì sao object chưa đổi, cần xác định cả trạng thái persistence context lẫn transaction/isolation level hiện tại.

## 3. Ví dụ hai transaction cập nhật cùng một tài khoản

Giả sử database có hàng:

| account_id | balance | version |
|---:|---:|---:|
| 42 | 100 | 5 |

Ứng dụng A mở T1 và nạp object. Ứng dụng B mở T2, cập nhật số dư thành 120 rồi commit.

```text
Thời gian ------------------------------------------------------------>

T1 / ORM A                         T2 / ORM B
--------------------------------   --------------------------------
BEGIN                              BEGIN
SELECT Account#42
object.balance = 100
                                   UPDATE balance = 120
                                   COMMIT
find(Account#42) lần nữa
ORM có thể trả object cũ: 100
```

Sau khi T2 commit, database lưu 120. Nhưng object đang managed trong T1 vẫn có thể là 100. Nếu ứng dụng hiển thị object này cho người dùng, người dùng thấy dữ liệu cũ dù một transaction khác đã cập nhật thành công.

Nếu T1 chỉ đọc để hiển thị và sau đó kết thúc, vấn đề có thể chỉ là độ mới của dữ liệu. Nếu T1 tiếp tục sửa object rồi flush, nguy cơ ghi đè thay đổi của T2 sẽ xuất hiện.

## 4. Vì sao query lại vẫn có thể trả object cũ?

Một hiểu lầm thường gặp là: “Nếu chạy lại câu query thì ORM chắc chắn sẽ thay object bằng giá trị mới.” Điều này không đúng với mọi kiểu query và mọi ORM.

Trong JPA/Hibernate, một entity đã managed trong persistence context được định danh bởi entity type và primary key. Khi query trả về cùng entity đó, ORM thường liên kết kết quả với instance đang được quản lý. Việc thực thi SQL mới không đồng nghĩa ORM sẽ ghi đè mọi field trong instance hiện tại.

Ví dụ:

```java
Account first = entityManager.find(Account.class, 42L);

// Transaction khác cập nhật balance và commit.

Account again = entityManager.find(Account.class, 42L);

System.out.println(first == again); // thường là true trong cùng context
System.out.println(again.getBalance()); // có thể vẫn là giá trị cũ
```

Với JPQL query, Hibernate có thể thực thi SQL để tìm các entity phù hợp. Nhưng nếu entity tương ứng đã có trong persistence context, kết quả có thể vẫn dùng instance managed hiện tại. Cần phân biệt việc query tìm ra hàng nào với việc ORM đồng bộ lại trạng thái của object đã tồn tại.

Các ORM khác cũng có cơ chế tương tự, nhưng chi tiết khác nhau:

- SQLAlchemy `Session` dùng identity map; truy vấn cùng primary key thường trả về instance đang được quản lý. Có thể dùng `refresh`, `expire` hoặc `populate_existing` tùy trường hợp.
- EF Core tracking query thường trả về entity đã được track và không ghi đè current/original values của entity đó chỉ vì query lại. Có thể dùng `Reload`, query no-tracking hoặc một `DbContext` mới.
- JPA/Hibernate dùng persistence context; `refresh`, `detach`, `clear` và `EntityManager` mới có semantics riêng.

## 5. Refresh: nạp lại trạng thái từ database

`refresh` yêu cầu ORM tải lại trạng thái của một object managed từ database. Đây là thao tác phù hợp khi ứng dụng muốn giữ object hiện tại nhưng cần đồng bộ field của nó với dữ liệu mà transaction hiện tại có thể nhìn thấy.

Ví dụ JPA:

```java
Account account = entityManager.find(Account.class, 42L);

// Một transaction khác cập nhật balance và commit.

entityManager.refresh(account);
System.out.println(account.getBalance());
```

`refresh` thường phát sinh truy vấn đọc lại hàng và đồng bộ trạng thái object. Nhưng cần hiểu hai giới hạn quan trọng:

1. `refresh` có thể ghi đè các thay đổi chưa flush của chính object đó trong bộ nhớ.
2. `refresh` vẫn tuân theo snapshot/isolation level của transaction hiện tại; nó không bảo đảm nhìn thấy mọi commit mới hơn snapshot.

Nếu object đang có thay đổi cục bộ cần giữ, hãy quyết định flush hoặc lưu những thay đổi đó trước khi refresh. Không gọi refresh một cách máy móc trên object dirty vì các giá trị chưa lưu có thể bị mất.

### 5.1. Refresh trong SQLAlchemy

Với SQLAlchemy:

```python
account = session.get(Account, 42)

# Một transaction khác đã cập nhật và commit.

session.refresh(account)
print(account.balance)
```

`Session.refresh()` phát sinh truy vấn để nạp lại các thuộc tính đã hết hạn/được yêu cầu từ database theo transaction hiện tại. Nếu transaction đang ở isolation level có snapshot cố định, giá trị trả về vẫn có thể là phiên bản cũ.

### 5.2. Reload trong EF Core

Với EF Core:

```csharp
var account = await db.Accounts.FindAsync(42);

// Một DbContext khác đã cập nhật và commit.

await db.Entry(account).ReloadAsync();
Console.WriteLine(account.Balance);
```

`ReloadAsync` làm mới giá trị được theo dõi từ database trong phạm vi transaction đang dùng. Nếu transaction snapshot chưa nhìn thấy commit khác, cần kết thúc transaction cũ và bắt đầu transaction mới theo yêu cầu nghiệp vụ.

## 6. Expire: đánh dấu trạng thái cần nạp lại khi truy cập

Thay vì nạp lại ngay, một ORM có thể đánh dấu thuộc tính hoặc object là expired. Khi ứng dụng truy cập thuộc tính sau đó, ORM sẽ phát sinh truy vấn để nạp lại dữ liệu.

SQLAlchemy cung cấp `expire` và `expire_all`:

```python
account = session.get(Account, 42)

# Một transaction khác commit thay đổi.

session.expire(account)
print(account.balance)  # truy vấn lại khi truy cập thuộc tính expired
```

Hoặc:

```python
session.expire_all()
```

`expire` hữu ích khi muốn giữ instance và chỉ trì hoãn việc đọc lại đến lúc cần. Nhưng nó không thay đổi isolation level. Nếu session vẫn ở trong transaction có snapshot cũ, lần tải lại có thể nhìn thấy dữ liệu theo snapshot đó.

Trong JPA/Hibernate, các thao tác tương ứng thường là `refresh` hoặc loại entity khỏi persistence context; JPA không có API `expire` chuẩn giống SQLAlchemy. Không nên chuyển tên API từ ORM này sang ORM khác mà giả định semantics giống nhau.

## 7. Detach, clear và tạo persistence context mới

Một cách khác là loại object khỏi vùng quản lý để lần truy cập sau không dùng lại instance cũ.

Trong JPA:

```java
entityManager.detach(account); // chỉ detach entity này

// Hoặc:
entityManager.clear();          // detach toàn bộ entity đang managed
```

Sau `detach`, object hiện tại trở thành detached. Gọi `find` lại có thể tạo hoặc nạp một instance managed mới. `clear` làm toàn bộ entity trong persistence context trở thành detached.

Trong Hibernate, `Session.evict(entity)` loại một entity khỏi session; `Session.clear()` loại tất cả. Với EF Core, có thể dùng một `DbContext` mới hoặc thay đổi tracking state; với SQLAlchemy, `expunge`/`expunge_all` detach instance khỏi session.

### 7.1. Cẩn thận với thay đổi chưa flush

Trước khi gọi `clear`, `detach` hoặc `expunge`, hãy xác định object có thay đổi cục bộ chưa được lưu hay không. Nếu ORM loại object khỏi context trước khi flush, thay đổi có thể không được ghi xuống database.

Trong JPA, có thể `flush` trước khi `clear` nếu cần lưu các thay đổi đang quản lý:

```java
entityManager.flush();
entityManager.clear();
```

Nhưng chỉ flush khi các thay đổi hiện tại hợp lệ và nên được ghi. `flush` không phải `commit`: transaction vẫn có thể rollback sau đó.

Nếu mục tiêu là đọc dữ liệu mới từ transaction mới, cách rõ ràng thường là kết thúc transaction cũ, đóng hoặc clear context theo vòng đời ứng dụng, rồi bắt đầu transaction/persistence context mới. Điều này tránh giữ snapshot cũ hoặc object cũ quá lâu.

## 8. Transaction mới có thể cần thiết để nhìn thấy commit mới

Ngay cả khi ORM thực sự phát sinh `SELECT` mới, database vẫn quyết định phiên bản nào có thể nhìn thấy theo isolation level.

### 8.1. READ COMMITTED

Ở nhiều DBMS, `READ COMMITTED` cho phép mỗi statement nhìn thấy những transaction khác đã commit trước khi statement bắt đầu. Vì vậy, nếu T1 thực hiện một câu `SELECT` mới sau khi T2 commit, database có thể trả giá trị mới.

Tuy nhiên, object managed trong identity map vẫn có thể giữ giá trị cũ nếu ORM không refresh nó. Có thể cần `refresh`, expire/reload hoặc một context mới.

### 8.2. REPEATABLE READ hoặc snapshot isolation

Ở isolation level giữ snapshot cho transaction, T1 có thể tiếp tục nhìn thấy trạng thái tại thời điểm snapshot được tạo, dù T2 đã commit. Một lần refresh trong cùng T1 không nhất thiết vượt qua snapshot đó.

Ví dụ khái quát:

```text
T1: BEGIN; lấy snapshot S1; đọc balance = 100
T2: UPDATE balance = 120; COMMIT
T1: refresh/query lại trong snapshot S1
    -> có thể vẫn thấy balance = 100
T1: COMMIT
T1 mới: BEGIN; snapshot mới; đọc balance = 120
```

Hành vi chi tiết của `REPEATABLE READ` khác nhau giữa PostgreSQL, InnoDB, SQL Server và Oracle. Một số hệ thống có snapshot theo transaction; một số có quy tắc locking hoặc update conflict riêng. Hãy xác nhận isolation semantics của DBMS đang dùng.

### 8.3. SERIALIZABLE

`SERIALIZABLE` có thể khiến transaction bị chờ hoặc bị hủy khi phát hiện xung đột không thể tuần tự hóa. Nếu transaction bị serialization failure, ứng dụng phải rollback và retry toàn bộ đơn vị công việc trong transaction mới. Chỉ refresh object không thể biến một transaction đã thất bại thành transaction hợp lệ.

## 9. Stale object có thể gây lost update

Rủi ro nghiêm trọng hơn việc hiển thị dữ liệu cũ là ghi đè thay đổi của transaction khác.

Giả sử balance ban đầu là 100. T1 nạp object với balance 100. T2 cập nhật balance thành 120 rồi commit. T1 vẫn giữ object cũ, cộng 10 rồi flush giá trị 110.

```text
T1 / ORM A                         T2 / ORM B
--------------------------------   --------------------------------
Đọc balance = 100
                                   UPDATE balance = 120
                                   COMMIT
Object trong A vẫn là 100
T1 cộng 10 -> object = 110
UPDATE balance = 110
COMMIT

Kết quả cuối = 110
Thay đổi 120 của T2 bị ghi đè.
```

Nếu nghiệp vụ mong muốn cộng thêm 10 vào số dư mới nhất, kết quả đúng phải là 130. Việc tính từ object cũ và ghi lại 110 đã làm mất cập nhật của T2.

Đây là lost update. Identity map khiến object cũ tiếp tục tồn tại; việc thiếu cơ chế phát hiện xung đột cho phép T1 ghi đè thay đổi đã commit.

## 10. Optimistic locking bằng version column

Optimistic locking phát hiện một object đã bị transaction khác thay đổi kể từ khi được nạp. ORM thường dùng một cột version hoặc timestamp để so sánh phiên bản khi cập nhật.

Ví dụ bảng:

| account_id | balance | version |
|---:|---:|---:|
| 42 | 100 | 5 |

T1 nạp version 5. T2 cập nhật balance và tăng version lên 6. Khi T1 flush, ORM gửi update có điều kiện version vẫn là 5. Vì database hiện có version 6, update của T1 không cập nhật được hàng nào và ORM báo optimistic locking conflict.

SQL khái quát:

```sql
UPDATE account
SET balance = 110,
    version = 6
WHERE account_id = 42
  AND version = 5;
```

Nếu row count là 0, object không còn là phiên bản hiện tại. Ứng dụng cần rollback và xử lý xung đột theo nghiệp vụ; thường là nạp lại dữ liệu, tính lại quyết định và retry toàn bộ transaction.

### 10.1. JPA @Version

```java
@Entity
public class Account {
    @Id
    private Long id;

    private BigDecimal balance;

    @Version
    private long version;
}
```

JPA provider dùng field `@Version` để kiểm tra xung đột khi cập nhật hoặc xóa entity versioned. Nếu version đã thay đổi, flush/commit có thể ném `OptimisticLockException`.

### 10.2. Hibernate và các ORM khác

Hibernate hỗ trợ version column qua `@Version`. SQLAlchemy có `version_id_col` trong mapper để kiểm tra version khi ORM flush instance. EF Core có thể cấu hình concurrency token như `rowversion` trong SQL Server hoặc một cột version do ứng dụng quản lý.

Ví dụ SQLAlchemy:

```python
class Account(Base):
    __tablename__ = "account"

    id = mapped_column(primary_key=True)
    balance = mapped_column(Numeric(12, 2))
    version_id = mapped_column(Integer, nullable=False)

    __mapper_args__ = {
        "version_id_col": version_id
    }
```

Ví dụ EF Core:

```csharp
public class Account
{
    public long Id { get; set; }
    public decimal Balance { get; set; }

    [Timestamp]
    public byte[] RowVersion { get; set; } = [];
}
```

Chi tiết cấu hình và kiểu dữ liệu version phụ thuộc ORM và DBMS. Version column không phải timestamp nghiệp vụ; nó là token để nhận biết phiên bản hàng.

### 10.3. Mọi đường ghi phải cập nhật version

Optimistic locking chỉ phát hiện thay đổi nếu mọi đường ghi liên quan tuân thủ giao thức version. Một câu SQL native hoặc batch update bên ngoài ORM có thể thay đổi `balance` nhưng không tăng `version`. Khi đó ORM đang giữ version cũ có thể không phát hiện thay đổi.

Nếu ứng dụng dùng SQL trực tiếp, stored procedure hoặc job ngoài ORM, cần bảo đảm chúng cũng cập nhật version/concurrency token hoặc có một cơ chế kiểm tra tương đương.

## 11. Pessimistic locking khi cần khóa trước khi sửa

Nếu xung đột thường xuyên hoặc nghiệp vụ cần tuần tự hóa cập nhật trên một hàng, có thể dùng pessimistic locking. Transaction lấy khóa database trước khi đọc/sửa để transaction khác phải chờ hoặc không thể lấy khóa xung đột.

JPA hỗ trợ lock mode:

```java
Account account = entityManager.find(
    Account.class,
    42L,
    LockModeType.PESSIMISTIC_WRITE
);

account.setBalance(account.getBalance().add(amount));
```

Hoặc dùng query lock:

```java
Account account = entityManager.createQuery(
    "select a from Account a where a.id = :id", Account.class)
    .setParameter("id", 42L)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getSingleResult();
```

Trong PostgreSQL, cơ chế tương ứng thường sử dụng `SELECT ... FOR UPDATE`. MySQL InnoDB, Oracle và SQL Server có locking syntax và semantics riêng.

Pessimistic lock phù hợp khi transaction cần đọc dữ liệu rồi chắc chắn sẽ cập nhật và xung đột thường xuyên. Đổi lại, transaction khác có thể phải chờ; giữ lock lâu làm tăng blocking và deadlock. Không gọi dịch vụ ngoài hoặc chờ người dùng trong lúc đang giữ lock.

### 11.1. Lock không tự làm object cũ mới lại

Nếu ORM đã nạp object trước khi lấy pessimistic lock, cần hiểu object đó có được refresh theo semantics của ORM hay không. Khóa hàng chỉ điều phối quyền truy cập trong database; nó không tự động thay thế giá trị đang nằm trong heap của ứng dụng.

Một luồng an toàn thường là bắt đầu transaction, lấy lock trước khi đọc dữ liệu cần quyết định, rồi thực hiện thay đổi trong cùng transaction. Nếu object đã được nạp từ trước, có thể cần refresh hoặc một persistence context mới sau khi lấy lock, tùy ORM.

## 12. Bulk update và native SQL có thể làm persistence context lệch

ORM thường theo dõi entity qua identity map. Nhưng một số thao tác cập nhật trực tiếp nhiều hàng không đi qua từng object managed.

Ví dụ JPQL bulk update:

```java
entityManager.createQuery(
    "update Account a set a.status = :status where a.lastLogin < :cutoff")
    .setParameter("status", AccountStatus.INACTIVE)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Bulk update tác động trực tiếp lên database. Các entity `Account` đã được nạp trước đó trong persistence context có thể vẫn giữ `status` cũ. JPA bulk update không đồng bộ tự động mọi entity managed với kết quả cập nhật; nó cũng bỏ qua một số semantics theo entity như dirty checking và callback thông thường. Ứng dụng thường cần `clear` hoặc refresh các entity bị ảnh hưởng sau khi flush những thay đổi cần giữ.

Tương tự, SQL native hoặc stored procedure có thể thay đổi dữ liệu mà ORM không biết. Sau khi chạy native DML, hãy xác định entity nào trong context có thể đã lỗi thời và làm mới/clear đúng phạm vi.

### 12.1. SQLAlchemy bulk DML

SQLAlchemy có các chiến lược đồng bộ session cho ORM-enabled bulk `UPDATE`/`DELETE`, như `synchronize_session` với các lựa chọn phù hợp. Nhưng SQL thô hoặc thao tác bên ngoài session có thể không đồng bộ identity map. Cần chọn synchronization strategy hoặc expire/refresh session sau DML.

### 12.2. EF Core ExecuteUpdate/ExecuteDelete

`ExecuteUpdate` và `ExecuteDelete` thực hiện DML trực tiếp trong database mà không tải và cập nhật từng entity đang tracked như `SaveChanges`. Entity đã tracked có thể vẫn chứa giá trị cũ. Có thể dùng `Reload`, tạo `DbContext` mới hoặc tránh trộn bulk DML với entity tracking trong cùng một luồng mà không có bước đồng bộ.

## 13. First-level cache và second-level cache

ORM có thể có nhiều tầng cache:

- **First-level cache:** cache gắn với session/persistence context. Nó thường tồn tại mặc định và giữ identity map.
- **Second-level cache:** cache dùng chung giữa nhiều session/context, thường do Hibernate hoặc provider bổ sung.
- **Query cache:** lưu kết quả định danh hoặc kết quả truy vấn theo cơ chế riêng của ORM/provider.
- **Application cache:** cache do ứng dụng tự xây dựng, ví dụ Redis hoặc local memory.

First-level cache là nguồn stale object thường gặp nhất trong một transaction dài. Second-level/query cache có thể khiến session mới cũng đọc dữ liệu cũ nếu cache invalidation hoặc cache concurrency strategy không phù hợp.

### 13.1. Second-level cache không phải nguồn sự thật độc lập

Nếu một transaction cập nhật hàng qua ORM, provider có thể cập nhật hoặc invalidate cache theo cấu hình. Nhưng nếu dữ liệu thay đổi từ SQL trực tiếp, một ứng dụng khác hoặc một hệ thống ngoài, cache có thể không nhận được tín hiệu invalidation.

Các chiến lược cache thường có những trade-off:

- Cache read-only phù hợp dữ liệu thực sự không thay đổi.
- Read-write hoặc nonstrict-read-write có quy tắc đồng bộ và mức nhất quán riêng.
- Transactional cache cần provider hỗ trợ phối hợp transaction phù hợp.
- Query cache có thể phụ thuộc timestamp/region invalidation và không nhất thiết lưu nguyên object mới nhất.

Không nên bật second-level cache cho dữ liệu thay đổi thường xuyên nếu chưa hiểu invalidation, eviction và transaction semantics. Với dữ liệu cần tính đúng đắn mạnh, đọc trực tiếp database hoặc dùng cache có giao thức version/invalidation rõ ràng có thể phù hợp hơn.

### 13.2. External writer có thể làm cache ORM lỗi thời

Nếu một batch job cập nhật bảng trực tiếp, ORM không nhất thiết biết cache nào cần xóa. Cần một trong các cách:

- Sau batch update, phát sự kiện invalidation cho cache liên quan.
- Evict entity/region/query cache theo API của provider.
- Dùng TTL ngắn nếu nghiệp vụ chấp nhận độ trễ nhất định.
- Không cache các entity có yêu cầu đọc mới nhất nghiêm ngặt.
- Đưa mọi đường ghi qua một service hoặc giao thức phát sự kiện thống nhất.

TTL chỉ giới hạn thời gian dữ liệu có thể cũ; nó không bảo đảm đọc nhất quán ngay lập tức.

## 14. Vòng đời persistence context ảnh hưởng đến độ mới

Persistence context tồn tại càng lâu, khả năng giữ object cũ càng lớn. Một số ứng dụng vô tình giữ `EntityManager`, Hibernate `Session`, SQLAlchemy `Session` hoặc EF `DbContext` lâu hơn phạm vi một đơn vị công việc.

Các nguyên tắc thường hữu ích:

- Dùng một persistence context ngắn cho mỗi request hoặc transaction nghiệp vụ phù hợp.
- Không giữ managed entity trong singleton hoặc cache ứng dụng qua nhiều request.
- Không dùng `DbContext` hoặc ORM session như object thread-safe dùng chung giữa nhiều luồng.
- Không lưu entity managed vào session web rồi dùng lại sau khi transaction đã kết thúc.
- Truyền ID hoặc DTO giữa các tầng thay vì giữ entity managed quá lâu.
- Khi cần dữ liệu mới, mở context/transaction phù hợp thay vì tái sử dụng context cũ không rõ trạng thái.

Một entity detached có thể được giữ trong ứng dụng, nhưng nó không tự cập nhật khi database thay đổi. Detached object cũng có thể trở thành stale; detach chỉ dừng ORM quản lý nó, không làm dữ liệu trong object mới hơn.

## 15. Entity graph và quan hệ có thể lỗi thời riêng

Một object cha có thể đã được nạp cùng một collection hoặc quan hệ con. Transaction khác có thể thêm, xóa hoặc thay đổi các hàng con. Khi đó, collection trong object cha có thể vẫn chứa danh sách cũ.

Ví dụ, T1 nạp `Order#500` và collection `items`. T2 thêm một `OrderItem` mới rồi commit. T1 vẫn giữ collection đã nạp trước đó; truy cập `order.getItems()` có thể trả danh sách cũ nếu collection đã được khởi tạo.

Refresh một entity cha không nhất thiết làm mới mọi collection/association trong mọi ORM. JPA có thể dùng `refresh` với cascade phù hợp; Hibernate có quy tắc riêng cho collection; SQLAlchemy có thể expire relationship attribute; EF Core cần reload navigation hoặc query lại trong context mới.

Khi dữ liệu quan hệ thay đổi ngoài context, cần xác định chính xác phần nào stale:

- Scalar field của entity cha.
- Collection một-nhiều.
- Reference nhiều-một.
- Join table hoặc association entity.
- Projection/DTO được tạo từ nhiều bảng.

Không giả định một lần refresh object gốc sẽ tự động đồng bộ mọi object con và mọi collection đang nằm trong memory.

## 16. DTO/projection và dữ liệu đã sao chép ra khỏi ORM

Khi ORM trả DTO hoặc projection, dữ liệu thường đã được sao chép vào object không còn được identity map quản lý như entity. DTO không tự cập nhật khi transaction khác commit.

Ví dụ:

```java
AccountSummary summary = entityManager.createQuery(
    "select new com.example.AccountSummary(a.id, a.balance) " +
    "from Account a where a.id = :id", AccountSummary.class)
    .setParameter("id", 42L)
    .getSingleResult();
```

`summary` là snapshot dữ liệu tại thời điểm query. Nếu transaction khác cập nhật balance, DTO hiện tại vẫn giữ giá trị cũ. Muốn cập nhật DTO, ứng dụng cần query lại hoặc xây dựng lại projection.

Đây là hành vi bình thường. DTO không có lifecycle đồng bộ với database; không nên kỳ vọng một object đã gửi tới frontend hoặc lưu trong cache sẽ tự thay đổi khi database commit.

## 17. Cách chọn thao tác làm mới dữ liệu

Không có một API duy nhất phù hợp mọi tình huống. Hãy chọn theo mục tiêu và trạng thái transaction:

| Mục tiêu | JPA/Hibernate | SQLAlchemy | EF Core |
|---|---|---|---|
| Nạp lại một entity managed | `EntityManager.refresh(entity)` / Hibernate refresh | `Session.refresh(obj)` | `Entry(entity).Reload()` |
| Đánh dấu dữ liệu cần tải lại khi truy cập | Không có API chuẩn JPA tương đương `expire` | `Session.expire(obj)` / `expire_all()` | Thường reload hoặc query bằng context mới |
| Loại entity khỏi identity map | `detach`, Hibernate `evict` | `expunge` | Detach tracking state |
| Loại mọi entity khỏi context | `clear` | `expunge_all` | Tạo `DbContext` mới hoặc detach theo phạm vi |
| Tránh tracking cho kết quả đọc | DTO/projection; query read-only phù hợp | `populate_existing`/Core query hoặc session riêng tùy nhu cầu | `AsNoTracking()` |
| Bắt đầu phạm vi đọc mới | Transaction/persistence context mới | Transaction/session phù hợp | Transaction/DbContext phù hợp |

Tên API là gợi ý theo framework; hãy kiểm tra phiên bản và cấu hình thực tế. Điều quan trọng là thao tác phải giải quyết đúng lớp đang gây stale: identity map, snapshot transaction, second-level cache hay DTO/application cache.

## 18. Quy trình chẩn đoán object cũ sau khi transaction khác commit

Khi ứng dụng đọc thấy giá trị cũ dù một transaction khác đã commit, hãy lần lượt kiểm tra:

1. **Object có đang managed không?** Xác định `EntityManager`/`Session`/`DbContext` nào đã nạp object và context đó có còn sống không.
2. **Có identity map hit không?** Kiểm tra ORM có trả lại instance cũ thay vì nạp lại từ database không.
3. **Query có thực sự phát SQL không?** Bật SQL logging hoặc tracing trong môi trường phù hợp để xác định ORM có gửi truy vấn hay không.
4. **Transaction đang ở isolation level nào?** Một snapshot cố định có thể không nhìn thấy commit mới trong cùng transaction.
5. **Có second-level/query/application cache không?** Xác định nguồn dữ liệu trả về và cơ chế invalidation.
6. **Dữ liệu được nạp thành entity, collection hay DTO?** Mỗi loại có cách làm mới khác nhau.
7. **Có bulk/native DML ngoài ORM không?** Những thao tác này có thể làm persistence context mất đồng bộ.
8. **Object có dirty state chưa flush không?** Refresh/clear có thể làm mất thay đổi cục bộ.
9. **Có version/concurrency token không?** Xác định thay đổi ngoài ORM có cập nhật token hay không.
10. **Cần độ mới ở mức nào?** Dữ liệu hiển thị có thể chấp nhận eventual consistency, còn số dư/tồn kho thường cần kiểm soát xung đột chặt hơn.

SQL logging cho biết ORM có truy vấn hay không; nó không tự chứng minh query nhìn thấy phiên bản mới. Cần kết hợp log với transaction timeline, isolation level và trạng thái cache.

## 19. Thiết kế ứng dụng để hạn chế stale object

### 19.1. Giữ persistence context trong phạm vi ngắn

Một context ngắn giúp object managed không tồn tại qua quá nhiều thay đổi từ transaction khác. Với ứng dụng web, một request hoặc một đơn vị công việc thường là phạm vi hợp lý, nhưng không nên mặc định mọi request đều cần cùng một cách mở transaction.

### 19.2. Dùng DTO cho dữ liệu đọc qua nhiều tầng

DTO làm rõ dữ liệu được chụp tại thời điểm truy vấn và tránh đưa entity managed ra khỏi lifecycle của ORM. Nếu cần cập nhật mới, query lại DTO theo ID hoặc điều kiện.

### 19.3. Dùng version column cho cập nhật cạnh tranh

Với dữ liệu mà việc ghi đè thay đổi của người khác là không chấp nhận được, cấu hình optimistic locking. Khi version thay đổi, transaction cũ phải xử lý conflict thay vì âm thầm ghi đè.

### 19.4. Dùng pessimistic lock cho tài nguyên nóng

Nếu xung đột thường xuyên và transaction cần quyền cập nhật trước khi ra quyết định, lấy lock trong transaction ngắn. Không giữ lock trong khi thực hiện công việc ngoài database.

### 19.5. Đồng bộ sau bulk/native update

Sau bulk DML, stored procedure hoặc SQL trực tiếp, refresh/expire/clear các entity có thể bị ảnh hưởng. Nếu nhiều entity hoặc quan hệ phức tạp, context mới thường dễ hiểu và an toàn hơn việc cố làm mới từng object rải rác.

### 19.6. Đặt cache policy theo yêu cầu nhất quán

Không cache dữ liệu thay đổi thường xuyên nếu chưa có invalidation rõ ràng. Với dữ liệu cần mới ngay, đọc từ database trong transaction phù hợp hoặc dùng cache có version/event invalidation được kiểm soát.

## 20. Ví dụ hoàn chỉnh: phát hiện xung đột bằng @Version

Giả sử ứng dụng cho phép người dùng chỉnh sửa thông tin tài khoản. T1 nạp entity version 5 và hiển thị form. Trong lúc người dùng chỉnh sửa, request khác cập nhật cùng hàng lên version 6.

Khi form cũ được gửi lại, ứng dụng không nên ghi đè dữ liệu mới mà không kiểm tra. Entity có `@Version` giúp provider phát hiện:

```java
@Entity
public class Account {
    @Id
    private Long id;

    private String displayName;

    private BigDecimal balance;

    @Version
    private long version;
}
```

Request có thể gửi version mà người dùng đã xem. Khi xử lý, ứng dụng nạp entity hiện tại và xác nhận version phù hợp; hoặc dùng update có điều kiện để DBMS chỉ ghi nếu version chưa đổi.

```sql
UPDATE account
SET display_name = :display_name,
    version = version + 1
WHERE account_id = :id
  AND version = :expected_version;
```

Nếu row count bằng 0, dữ liệu đã thay đổi sau khi form được tải. Ứng dụng có thể trả conflict, hiển thị thay đổi mới để người dùng hợp nhất hoặc yêu cầu xác nhận lại. Không nên tự động retry với cùng payload cũ nếu điều đó có thể ghi đè quyết định mới của người dùng khác.

## 21. Những hiểu lầm thường gặp

- **Gọi `find` lần nữa là chắc chắn đọc mới.** Trong cùng persistence context, ORM có thể trả instance đang managed.
- **ORM query có SQL mới là object sẽ được ghi đè.** Kết quả entity có thể được liên kết với instance cũ; cần refresh/expire theo ORM.
- **Refresh luôn thấy commit mới nhất.** Snapshot isolation có thể khiến transaction hiện tại vẫn nhìn thấy phiên bản cũ.
- **Detach làm object mới.** Detach chỉ dừng tracking; dữ liệu trong object vẫn là giá trị đã nạp trước đó.
- **Clear luôn an toàn.** Entity dirty chưa flush có thể mất thay đổi khi bị detach.
- **Pessimistic lock tự cập nhật object.** Lock điều phối database; object trong memory vẫn cần được nạp/refresh đúng thời điểm.
- **Bulk update đồng bộ mọi entity đang tracked.** Nhiều ORM không tự cập nhật persistence context sau bulk/native DML.
- **Version column phát hiện mọi thay đổi từ mọi nguồn.** Đường ghi ngoài ORM phải cập nhật concurrency token để cơ chế phát hiện hoạt động.
- **Second-level cache luôn invalidated khi SQL ngoài ORM chạy.** Cache provider có thể không biết thay đổi đó.
- **DTO tự cập nhật theo database.** DTO là dữ liệu đã sao chép và cần query lại khi muốn giá trị mới.

## 22. Những điểm cần ghi nhớ

- ORM giữ object trong identity map/persistence context để bảo đảm identity và theo dõi thay đổi; object có thể trở thành stale sau khi transaction khác commit.
- Cùng một persistence context, `find` hoặc tracking query có thể trả instance cũ thay vì làm mới mọi field.
- `refresh`, `expire`, `reload`, `detach`, `clear` và context mới giải quyết các nhu cầu khác nhau; chọn API theo ORM.
- Refresh vẫn chịu ảnh hưởng isolation level. Với snapshot cố định, có thể cần kết thúc transaction và bắt đầu transaction mới để nhìn thấy commit mới.
- Stale object có thể gây lost update nếu ứng dụng ghi lại giá trị được tính từ dữ liệu cũ.
- Optimistic locking bằng version column phát hiện thay đổi cạnh tranh; mọi đường ghi cần cập nhật version.
- Pessimistic locking phù hợp khi cần khóa tài nguyên trước khi đọc/sửa, nhưng làm tăng blocking và cần transaction ngắn.
- Bulk/native DML và thao tác từ hệ thống ngoài có thể làm persistence context hoặc second-level cache mất đồng bộ.
- Entity collection, DTO và application cache có thể stale độc lập với entity gốc.
- Theo dõi vòng đời context, SQL log, isolation level, cache và version token để xác định đúng nguồn dữ liệu cũ.

Khi một transaction khác đã commit mà object trong ứng dụng vẫn giữ giá trị cũ, hãy xác định dữ liệu đang nằm ở lớp nào: identity map, snapshot transaction, cache cấp hai hay DTO/application cache. Sau đó chọn cách làm mới hoặc bắt đầu phạm vi đọc mới phù hợp. Với thao tác ghi, kết hợp optimistic/pessimistic concurrency để ngăn object cũ âm thầm ghi đè thay đổi đã commit.
