# Ảnh hưởng đến khóa, ràng buộc và thuộc tính bắt buộc

## 1. Kế thừa entity làm thay đổi cấu trúc ràng buộc như thế nào?

Trong lập trình hướng đối tượng, một lớp con kế thừa thuộc tính và hành vi của lớp cha. Nhưng trong cơ sở dữ liệu quan hệ, **bảng, khóa chính, khóa ngoại, ràng buộc `NOT NULL` và `UNIQUE`** phải được đặt lên những cột vật lý cụ thể. Vì vậy, khi ánh xạ một hệ phân cấp entity bằng Jakarta Persistence (JPA) với Hibernate ORM, chiến lược kế thừa ảnh hưởng trực tiếp đến:

- Số lượng bảng và vị trí lưu những thuộc tính kế thừa.
- Vị trí và phạm vi của **primary key** (PK), **foreign key** (FK).
- Khả năng bảo đảm một giá trị **duy nhất trên cả hệ phân cấp**, thay vì chỉ trên từng subtype.
- Cách khai báo thuộc tính **bắt buộc ở mọi subtype** và thuộc tính **chỉ bắt buộc ở một subtype**.
- Khả năng dùng `NOT NULL`, `CHECK`, `UNIQUE` và `FOREIGN KEY` của database để bảo vệ dữ liệu.
- Cách các entity khác tham chiếu đến lớp cha hoặc một lớp con cụ thể.
- Khả năng thay đổi schema và dữ liệu khi bổ sung subtype mới.

Ba chiến lược kế thừa entity chuẩn được khai báo qua `@Inheritance`:

~~~java
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@Inheritance(strategy = InheritanceType.JOINED)
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
~~~

Mỗi lần chọn **một** chiến lược cho hệ phân cấp tương ứng, không đồng thời gắn cả ba.

Để đi xuyên suốt bài học, dùng hệ thống quản lý tài sản:

~~~text
                  Asset (lớp cha trừu tượng)
                     id: Long
                     assetCode: String
                     displayName: String
                       /       \
                      /         \
              BookAsset       LaptopAsset
                isbn             serialNumber
~~~

Quy tắc nghiệp vụ:

1. Mọi tài sản đều có một định danh `id`, mã `assetCode` và tên `displayName`.
2. `assetCode` phải không rỗng và **duy nhất trên toàn bộ tài sản**, không phân biệt loại.
3. Sách phải có `isbn`; laptop phải có `serialNumber`.
4. `isbn` chỉ có ý nghĩa với sách; `serialNumber` chỉ có ý nghĩa với laptop.
5. Không cho hai sách trùng ISBN, không cho hai laptop trùng serial number.
6. Một tác vụ khác có thể tham chiếu tới `Asset` nói chung mà không cần biết đó là sách hay laptop.

Điểm khó nằm ở yêu cầu 2, 3, 4 và 6: những quy tắc này có được database thực thi đơn giản hay phải bổ sung cấu trúc dữ liệu khác còn phụ thuộc chiến lược kế thừa.

## 2. Phân biệt kế thừa Java, entity hierarchy và bảng dữ liệu

Kế thừa trong Java:

~~~java
public abstract class Asset {
    protected String assetCode;
}

public class BookAsset extends Asset {
    private String isbn;
}
~~~

chỉ cho thấy quan hệ giữa **các lớp Java**. Nó chưa khẳng định dữ liệu nằm trong một bảng hay nhiều bảng.

Khi dùng JPA, cần quyết định lớp cha là:

- **`@Entity`**: một entity root của hệ phân cấp. Các subclass `@Entity` tham gia quan hệ đa hình, ví dụ `select a from Asset a`.
- **`@MappedSuperclass`**: chỉ cung cấp mapping kế thừa cho các entity con; bản thân lớp cha không phải entity được quản lý, không có bảng riêng và không phải mục tiêu trực tiếp của một truy vấn entity đa hình chuẩn.

Nếu lớp cha là entity và không chọn `@Inheritance`, chiến lược mặc định của Jakarta Persistence là **`SINGLE_TABLE`**. Dù có mặc định, khai báo tường minh thường giúp người đọc hiểu rõ schema mà nhóm đã chọn.

### 2.1. Khóa chính không phải là “mỗi class con có một ID riêng”

Trong một hierarchy có entity root, ID biểu diễn **định danh của entity**. Với `SINGLE_TABLE` và `JOINED`, có thể dễ thấy ID chung qua một bảng gốc. Với `TABLE_PER_CLASS`, mỗi concrete subtype có bảng riêng nhưng Hibernate vẫn cần quản lý các entity một cách nhất quán, bao gồm truy vấn đa hình và định danh giữa các subtype.

Không nên giả định mỗi bảng con có thể tự phát sinh ID từ 1 mà không liên quan tới bảng còn lại; đặc biệt với `TABLE_PER_CLASS`, Hibernate cần một cơ chế sinh ID bảo đảm tính duy nhất trên hệ phân cấp trong các ngữ cảnh sử dụng entity đa hình.

### 2.2. Ràng buộc ở Java và database là hai tầng khác nhau

Ví dụ:

~~~java
@Column(nullable = false, unique = true, length = 40)
private String assetCode;
~~~

Các lựa chọn ở `@Column` mô tả **metadata ánh xạ và DDL dự kiến**. Chúng không biến mọi thay đổi của mã Java thành migration, cũng không tự ngăn mọi đường ghi ngoài ORM.

Nếu database đã có bảng không chứa ràng buộc `UNIQUE`, việc thêm `unique = true` trong entity không bảo đảm constraint xuất hiện trong production. Ngược lại, khi database có constraint thật, nó có thể từ chối một giao dịch dù object đã qua validation ở Java.

Cần phân biệt:

| Tầng | Ví dụ | Bảo đảm gì? |
|---|---|---|
| Mô hình Java | Constructor yêu cầu mã sách | Có thể chặn cách tạo object nhất định |
| Bean Validation | `@NotBlank` trên `isbn` | Kiểm tra giá trị khi validation được thực thi/tích hợp |
| JPA metadata | `@Column(nullable = false)` | Cung cấp thông tin mapping, schema generation và hành vi provider tương ứng |
| Ràng buộc database | `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` | DB kiểm tra mọi đường ghi chịu ràng buộc đó |
| Business transaction | Kiểm tra thay đổi loại, tạo/xóa tài sản | Phối hợp các quy tắc liên bảng, đồng thời và vòng đời |

Một thiết kế đáng tin cậy phải xác định **ràng buộc quan trọng cần được bảo vệ ở tầng nào**, đặc biệt với dữ liệu được nhiều dịch vụ hoặc script cùng ghi.

## 3. Ba chiến lược kế thừa và phạm vi khóa/ràng buộc

| Đặc điểm | `SINGLE_TABLE` | `JOINED` | `TABLE_PER_CLASS` |
|---|---|---|---|
| Bảng vật lý | Một bảng cho cả hierarchy | Bảng cha và bảng cho subtype | Mỗi concrete subtype một bảng |
| PK entity | Một PK ở bảng chung | PK bảng cha; bảng con dùng PK đồng thời làm FK | PK ở từng bảng con |
| FK kế thừa giữa bảng cha/con | Không cần | Có, từ PK bảng con sang PK bảng cha | Không có bảng cha chung để nối |
| Cột chung như `assetCode` | Một cột ở bảng chung | Một cột ở bảng cha | Lặp lại trên từng bảng con |
| `UNIQUE(assetCode)` trên cả hierarchy | Đơn giản trên bảng chung | Đơn giản trên bảng cha | Không thể bảo đảm chỉ bằng UNIQUE riêng tại từng bảng con |
| Cột `isbn` dành riêng cho Book | Có trong bảng chung, thường nullable | Nằm ở bảng Book, có thể `NOT NULL` | Nằm ở bảng Book, có thể `NOT NULL` |
| Phân biệt subtype | Thường qua discriminator | Qua bảng con, có thể kết hợp discriminator tùy mapping | Qua bảng nguồn trong truy vấn đa hình |
| Truy vấn đa hình | Đọc bảng chung | Có thể phải join các bảng subclass | Thường phải union dữ liệu các bảng concrete |
| FK từ bảng khác đến `Asset` | Trỏ bảng chung | Trỏ bảng cha | Không có một bảng `assets` chung để FK tới |
| Thêm subtype mới | Thêm giá trị loại và các cột tương ứng | Thêm bảng subtype | Thêm bảng concrete |

Bảng này cho thấy **một quyết định ORM đồng thời là quyết định về khả năng thực thi ràng buộc bằng DDL**.

## 4. SINGLE_TABLE: một khóa chính và mọi subtype dùng chung một bảng

### 4.1. Entity root và hai subtype

Trong `SINGLE_TABLE`, tất cả bản ghi được lưu vào một bảng, chẳng hạn `assets`. Cột discriminator phân biệt bản ghi là sách hay laptop.

~~~java
package example.assets;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "asset_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 12
)
public abstract class Asset {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "asset_seq")
    @SequenceGenerator(
        name = "asset_seq",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, unique = true, length = 40)
    private String assetCode;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    protected Asset() {}

    protected Asset(String assetCode, String displayName) {
        this.assetCode = assetCode;
        this.displayName = displayName;
    }

    public Long getId() { return id; }
    public String getAssetCode() { return assetCode; }
    public String getDisplayName() { return displayName; }
}
~~~

Subtype sách:

~~~java
package example.assets;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("BOOK")
public class BookAsset extends Asset {

    // Cột vật lý được dùng chung với các subtype khác.
    // Bản ghi LAPTOP không có ISBN, nên tránh NOT NULL toàn cột.
    @Column(name = "isbn", length = 17, unique = true)
    private String isbn;

    protected BookAsset() {}

    public BookAsset(String code, String name, String isbn) {
        super(code, name);
        this.isbn = isbn;
    }

    public String getIsbn() { return isbn; }
}
~~~

Subtype laptop:

~~~java
package example.assets;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("LAPTOP")
public class LaptopAsset extends Asset {

    @Column(name = "serial_number", length = 80, unique = true)
    private String serialNumber;

    protected LaptopAsset() {}

    public LaptopAsset(String code, String name, String serialNumber) {
        super(code, name);
        this.serialNumber = serialNumber;
    }

    public String getSerialNumber() { return serialNumber; }
}
~~~

Trong các entity trên:

- `Asset` là entity root có mapping `@Id` duy nhất của hierarchy.
- `@DiscriminatorColumn` khai báo cột xác định loại entity. Hai subtype có `@DiscriminatorValue` khác nhau.
- `assetCode` và `displayName` thuộc lớp cha nên tất cả bản ghi đều có chúng.
- `isbn` chỉ thuộc `BookAsset`; `serialNumber` chỉ thuộc `LaptopAsset` nhưng cả hai cột vẫn nằm trên **cùng bảng `assets`**.
- Không cần định nghĩa khóa chính thứ hai hoặc `@JoinColumn` giữa BookAsset và Asset: không có bảng con nào để join.

### 4.2. Sơ đồ dữ liệu vật lý

~~~text
                      BẢNG assets
+----+------------+------------+--------------+------------+---------------+
| id | asset_kind | asset_code | display_name | isbn       | serial_number |
+----+------------+------------+--------------+------------+---------------+
|  1 | BOOK       | A-001      | Java Basics  | 978...     | NULL          |
|  2 | LAPTOP     | A-002      | Workstation  | NULL       | SN-2026-A     |
|  3 | BOOK       | A-003      | SQL Guide    | 979...     | NULL          |
+----+------------+------------+--------------+------------+---------------+
               Một PK và một phạm vi UNIQUE(asset_code)
~~~

Dữ liệu này giải thích vì sao `SINGLE_TABLE` dễ truy vấn đa hình và dễ áp dụng unique constraint trên thuộc tính chung: **mọi hàng của hierarchy đều có mặt trong một bảng**.

### 4.3. Ràng buộc NOT NULL chung và NOT NULL theo subtype

Có thể áp dụng `NOT NULL` trực tiếp trên:

- `id`: primary key.
- `asset_kind`: discriminator, nếu schema và chiến lược ghi yêu cầu.
- `asset_code`: mọi tài sản đều có mã.
- `display_name`: mọi tài sản đều có tên.

Nhưng **không thể đơn giản đặt `NOT NULL` lên toàn bộ cột `isbn`** nếu những hàng laptop cần giá trị `NULL`. Tương tự, `serial_number` phải cho phép null ở những hàng sách.

Vì vậy, trong mapping `SINGLE_TABLE`, không nên dùng `@Column(nullable = false)` một cách máy móc trên mọi thuộc tính của subclass. Ràng buộc kiểu đó có thể khiến DDL `NOT NULL` mâu thuẫn với dữ liệu của subtype khác, tùy provider và cách sinh schema.

Tuy nhiên, việc cột vật lý cho phép `NULL` **không đồng nghĩa ISBN được phép thiếu ở một BookAsset**. Để bảo vệ quy tắc này ở DB, có thể dùng một `CHECK` có điều kiện theo discriminator.

### 4.4. Ví dụ schema PostgreSQL có CHECK theo subtype

DDL minh họa cho hierarchy `SINGLE_TABLE`:

~~~sql
CREATE SEQUENCE asset_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_kind VARCHAR(12) NOT NULL,
    asset_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    isbn VARCHAR(17),
    serial_number VARCHAR(80),

    CONSTRAINT uk_assets_code UNIQUE (asset_code),
    CONSTRAINT uk_assets_isbn UNIQUE (isbn),
    CONSTRAINT uk_assets_serial UNIQUE (serial_number),

    CONSTRAINT ck_assets_subtype_fields CHECK (
        (asset_kind = 'BOOK'
            AND isbn IS NOT NULL
            AND serial_number IS NULL)
        OR
        (asset_kind = 'LAPTOP'
            AND isbn IS NULL
            AND serial_number IS NOT NULL)
    )
);
~~~

Ứng dụng dùng `@SequenceGenerator` để lấy ID từ `asset_id_seq`; vì vậy trong ví dụ ORM có thể cấp ID trước khi `INSERT`. DDL trên là thiết kế schema minh họa cho PostgreSQL, không cam kết Hibernate sẽ sinh đúng từng dòng SQL ở mọi dialect.

Ý nghĩa của `CHECK`:

- Hàng `BOOK` bắt buộc có `isbn`, không mang `serial_number`.
- Hàng `LAPTOP` bắt buộc có `serial_number`, không mang `isbn`.
- Các giá trị discriminator ngoài `BOOK`/`LAPTOP` không qua được CHECK này.
- Quy tắc được kiểm tra tại DB, kể cả khi dữ liệu được ghi bằng SQL ngoài ORM.

Nếu hệ thống cho phép một subtype khác hoặc cho phép một số subtype bổ sung cả hai trường, CHECK phải thay đổi theo đúng nghiệp vụ. **Không nên đưa ràng buộc theo subtype vào migration rồi quên cập nhật khi thêm class con.**

Với database hỗ trợ CHECK khác nhau, cú pháp và tính năng phải được xác nhận theo hệ quản trị và phiên bản; một số phiên bản DB cũ có thể xử lý CHECK khác mong đợi. Các ràng buộc trong migration cần được xác nhận trên hệ DB mục tiêu.

### 4.5. UNIQUE trên cột subclass và giá trị NULL

`UNIQUE(isbn)` trên bảng chung có thể ngăn hai sách dùng cùng giá trị ISBN. Nhưng các hàng laptop sẽ có `isbn = NULL`. Nhiều hệ DB cho phép nhiều giá trị NULL trong unique constraint, song quy tắc chính xác đối với NULL và unique index khác nhau giữa các hệ quản trị.

Với PostgreSQL, có thể cân nhắc một unique index có điều kiện:

~~~sql
CREATE UNIQUE INDEX uk_assets_book_isbn
    ON assets (isbn)
    WHERE asset_kind = 'BOOK';

CREATE UNIQUE INDEX uk_assets_laptop_serial
    ON assets (serial_number)
    WHERE asset_kind = 'LAPTOP';
~~~

Hai index này minh họa **unique scope theo subtype**. Nếu đã tạo unique constraints toàn cột như DDL trước đó, không nên thêm index trùng một cách vô ích; chọn một thiết kế phù hợp với query, dữ liệu và yêu cầu vận hành. Partial index ở đây là tính năng PostgreSQL; không phải DDL portable của JPA.

### 4.6. Nguy cơ khi dùng @NotNull/@NotBlank của Bean Validation

Có thể đặt validation nghiệp vụ lên thuộc tính của subclass:

~~~java
import jakarta.validation.constraints.NotBlank;

@Entity
@DiscriminatorValue("BOOK")
public class BookAsset extends Asset {

    @NotBlank
    @Column(name = "isbn", length = 17)
    private String isbn;

    // ...
}
~~~

`@NotBlank` có ý nghĩa **ở các instance BookAsset được validation**, không có nghĩa tất cả hàng trong bảng `assets` phải có ISBN. Tuy nhiên, nếu một hệ thống schema generation tích hợp Bean Validation để suy ra `NOT NULL` từ annotation validation, phải kiểm tra chính xác DDL và cấu hình đó. Tránh để cơ chế DDL tự suy luận tạo constraint mâu thuẫn với `SINGLE_TABLE`.

Quy tắc an toàn là: **validation có điều kiện theo subtype ở tầng Java; DB dùng CHECK có điều kiện theo discriminator** nếu yêu cầu bảo vệ toàn vẹn ở mọi đường ghi.

### 4.7. Một giới hạn của SINGLE_TABLE: dữ liệu subtype cũ và subtype mới

Giả sử sau này có `VehicleAsset` với `licensePlate` bắt buộc. Cần:

1. Thêm mapping subtype và giá trị discriminator mới, ví dụ `VEHICLE`.
2. Thêm cột `license_plate` có thể null trên bảng chung, vì các hàng hiện có là BOOK/LAPTOP.
3. Cập nhật CHECK để yêu cầu `license_plate IS NOT NULL` khi `asset_kind = 'VEHICLE'`.
4. Xem xét unique/index riêng cho biển số.
5. Xác định migration và rollout giữa ứng dụng cũ/mới để không từ chối các bản ghi được triển khai trong thời gian chuyển đổi.

Nếu hệ phân cấp có nhiều subtype với nhiều trường riêng, bảng chung sẽ có nhiều cột null theo loại. Điều này không sai về bản chất, nhưng khiến việc thể hiện những ràng buộc chỉ áp dụng cho một subtype bằng DDL phức tạp hơn.
## 5. JOINED: PK bảng con đồng thời là FK tới bảng cha

`JOINED` tách những thuộc tính chung vào bảng cha và những thuộc tính riêng vào bảng con. Mỗi entity subclass được biểu diễn bằng **một hàng trong bảng cha và một hàng trong bảng subtype**, cùng một định danh.

### 5.1. Khai báo mapping

Lớp cha giữ `@Entity`, `@Id`, `@GeneratedValue` và các trường chung như ở ví dụ trước, nhưng chọn:

~~~java
@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Asset {
    // @Id, @GeneratedValue, assetCode, displayName
    // giữ như phần SINGLE_TABLE.
}
~~~

Các thuộc tính kế thừa **không cần khai báo lại** ở từng subclass. Với subclass sách, bảng riêng chứa những cột của sách:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_assets")
@PrimaryKeyJoinColumn(name = "id", referencedColumnName = "id")
public class BookAsset extends Asset {

    @Column(name = "isbn", nullable = false, unique = true, length = 17)
    private String isbn;

    protected BookAsset() {}

    public BookAsset(String code, String name, String isbn) {
        super(code, name);
        this.isbn = isbn;
    }

    public String getIsbn() { return isbn; }
}
~~~

Subtype laptop:

~~~java
@Entity
@Table(name = "laptop_assets")
@PrimaryKeyJoinColumn(name = "id", referencedColumnName = "id")
public class LaptopAsset extends Asset {

    @Column(name = "serial_number", nullable = false, unique = true, length = 80)
    private String serialNumber;

    protected LaptopAsset() {}

    public LaptopAsset(String code, String name, String serialNumber) {
        super(code, name);
        this.serialNumber = serialNumber;
    }
}
~~~

Các đoạn trên minh họa một **phương án thay thế** cho toàn bộ hierarchy `SINGLE_TABLE` ở phần trước; không dùng hai bộ định nghĩa `Asset` cùng lúc trong một ứng dụng. Import các annotation cần thiết cho subtype laptop tương tự subclass sách. `@PrimaryKeyJoinColumn` cho biết cột PK tại bảng subtype dùng để tham chiếu cột PK của bảng gốc; khi tên mặc định đã đúng, có thể không cần viết tường minh.

Điểm khác biệt lớn: với `JOINED`, `isbn` tồn tại **chỉ trong bảng `book_assets`**, nên `nullable = false` và `UNIQUE` có thể diễn đạt trực tiếp trên cột này mà không gây mâu thuẫn với những hàng laptop.

### 5.2. DDL minh họa

~~~sql
CREATE SEQUENCE asset_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    CONSTRAINT uk_assets_code UNIQUE (asset_code)
);

CREATE TABLE book_assets (
    id BIGINT PRIMARY KEY,
    isbn VARCHAR(17) NOT NULL,
    CONSTRAINT fk_book_asset
        FOREIGN KEY (id) REFERENCES assets(id),
    CONSTRAINT uk_book_isbn UNIQUE (isbn)
);

CREATE TABLE laptop_assets (
    id BIGINT PRIMARY KEY,
    serial_number VARCHAR(80) NOT NULL,
    CONSTRAINT fk_laptop_asset
        FOREIGN KEY (id) REFERENCES assets(id),
    CONSTRAINT uk_laptop_serial UNIQUE (serial_number)
);
~~~

Mỗi bảng con dùng `id` vừa làm khóa chính, vừa làm khóa ngoại đến `assets.id`. Sơ đồ:

~~~text
                          assets
               +--------------------------+
               | id PK                    |
               | asset_code UNIQUE NOT NULL|
               | display_name NOT NULL    |
               +--------------------------+
                         ^        ^
                         |        |
                  PK/FK id        PK/FK id
                         |        |
             book_assets          laptop_assets
        +------------------+  +---------------------+
        | id PK, FK        |  | id PK, FK           |
        | isbn NOT NULL    |  | serial_number       |
        |      UNIQUE      |  |     NOT NULL UNIQUE |
        +------------------+  +---------------------+
~~~

Một object `BookAsset` với ID 10 có một hàng `assets.id = 10` và một hàng `book_assets.id = 10`. Giá trị `assetCode` không được sao chép xuống bảng `book_assets` vì nó đã được quản lý ở bảng gốc.

### 5.3. Bảng con có thể áp dụng NOT NULL riêng

Khác `SINGLE_TABLE`, giờ `book_assets.isbn` không cần có giá trị dành cho laptop: bảng `book_assets` **không có hàng laptop**. Vì vậy:

~~~sql
isbn VARCHAR(17) NOT NULL UNIQUE
~~~

có nghĩa đúng với toàn bộ những hàng trong bảng `book_assets`. Tương tự, `laptop_assets.serial_number` có thể `NOT NULL` trực tiếp.

Điều này giúp `JOINED` phù hợp khi mỗi subtype có nhiều trường bắt buộc riêng, đặc biệt khi muốn DB bảo vệ ràng buộc rõ ràng mà không cần xây `CHECK` lớn dựa vào discriminator.

### 5.4. Ràng buộc chung nằm ở bảng cha

`UNIQUE(asset_code)` đặt trên `assets` có hiệu lực cho cả sách lẫn laptop, vì mọi entity của hierarchy đều được biểu diễn bằng một hàng ở bảng cha. Tương tự, `display_name NOT NULL` áp dụng chung.

Điểm này khác `TABLE_PER_CLASS`: thuộc tính chung không bị lặp lại, nên phạm vi unique toàn hệ phân cấp rất tự nhiên.

### 5.5. FK child-to-parent bảo đảm điều gì, và chưa bảo đảm điều gì?

Constraint:

~~~sql
FOREIGN KEY (id) REFERENCES assets(id)
~~~

bảo đảm không thể có hàng `book_assets` trỏ đến một `assets.id` không tồn tại. Nhưng **chỉ bằng constraint đó**, DB chưa chắc bảo đảm:

- Mỗi hàng `assets` có đúng một hàng trong một bảng subtype.
- Một hàng `assets.id = 10` không đồng thời xuất hiện trong cả `book_assets` và `laptop_assets`.
- Khi có thêm discriminator ở bảng cha, giá trị discriminator luôn khớp với bảng subtype đã chứa hàng.

Hibernate dựa trên mapping inheritance và các thao tác ORM để giữ mô hình thông thường nhất quán. Nhưng script SQL khác có thể tạo hàng cha thiếu hàng con, hoặc tạo dữ liệu không phản ánh đúng một subtype, nếu schema không có ràng buộc bổ sung.

Nếu cần bảo vệ nghiêm ngặt cả khi ghi trực tiếp vào DB, phải đánh giá trigger, ràng buộc nâng cao hoặc kiến trúc schema khác theo hệ quản trị. Đây là ràng buộc liên bảng, không thể diễn đạt chỉ bằng `NOT NULL` trên một cột.

### 5.6. Persist và delete trong JOINED

Persist một `BookAsset` thường cần ghi hai hàng với cùng ID:

~~~text
1. Hibernate lấy id từ sequence / generator.
2. INSERT INTO assets (id, asset_code, display_name) ...
3. INSERT INTO book_assets (id, isbn) ...
4. Commit transaction.
~~~

Vì bảng con FK đến bảng cha, thứ tự ghi phải phù hợp với ràng buộc. Nếu cả hai thao tác cùng transaction và có lỗi ở bước insert sách, transaction có thể rollback, tránh để lại nửa entity khi được quản lý đúng.

Khi xóa entity, ORM có thể phải xử lý bảng con trước bảng cha để đáp ứng FK. Cơ chế `ON DELETE CASCADE` của database và cascade của JPA là hai lựa chọn khác nhau; không mặc định mỗi FK trong JOINED đều có `ON DELETE CASCADE` nếu mapping/DDL không quy định.

### 5.7. Đổi loại entity không chỉ là đổi một giá trị

Với `SINGLE_TABLE`, subtype được thể hiện qua discriminator và cột riêng. Với `JOINED`, subtype còn thể hiện qua **sự tồn tại của hàng ở bảng con**. Nếu nghiệp vụ muốn “biến một BookAsset thành LaptopAsset”, đó có thể là thay đổi kiểu entity trong mô hình Java và thay cấu trúc các hàng liên quan.

JPA không được thiết kế để một managed entity đổi runtime class đơn giản như đặt setter. Thường phải xác định quy tắc tạo/xóa entity, chuyển dữ liệu và các FK tham chiếu; trong một số nghiệp vụ, thay thuộc tính phân loại có thể hợp lý hơn kế thừa entity thực sự.

## 6. TABLE_PER_CLASS: mỗi concrete subtype là một bảng độc lập

Với `TABLE_PER_CLASS`, những cột kế thừa từ `Asset` được lặp lại vào **mỗi bảng concrete subclass**. Không có bảng cha chung chứa một hàng cho mọi entity trong hierarchy.

### 6.1. Mapping

Giữ root là `@Entity` với ID và các thuộc tính chung, nhưng chuyển sang:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Asset {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "asset_seq")
    @SequenceGenerator(
        name = "asset_seq",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, length = 40)
    private String assetCode;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    protected Asset() {}

    protected Asset(String code, String name) {
        this.assetCode = code;
        this.displayName = name;
    }
}
~~~

Subtype:

~~~java
@Entity
@Table(name = "book_assets")
public class BookAsset extends Asset {

    @Column(name = "isbn", nullable = false, unique = true, length = 17)
    private String isbn;

    protected BookAsset() {}

    public BookAsset(String code, String name, String isbn) {
        super(code, name);
        this.isbn = isbn;
    }
}
~~~

~~~java
@Entity
@Table(name = "laptop_assets")
public class LaptopAsset extends Asset {

    @Column(name = "serial_number", nullable = false, unique = true, length = 80)
    private String serialNumber;

    protected LaptopAsset() {}

    public LaptopAsset(String code, String name, String serialNumber) {
        super(code, name);
        this.serialNumber = serialNumber;
    }
}
~~~

Trong `TABLE_PER_CLASS`, Hibernate thường cần một cơ chế cấp ID **chia sẻ trên hierarchy**, chẳng hạn sequence dùng chung. `GenerationType.IDENTITY`, vốn dựa trên IDENTITY tự sinh riêng ở từng bảng, không phù hợp và không được Hibernate hỗ trợ cho chiến lược union-subclass thông thường. Đây là một điểm cần kiểm tra khi thay đổi từ `SINGLE_TABLE` hoặc `JOINED`.

### 6.2. DDL minh họa

~~~sql
CREATE SEQUENCE asset_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE book_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    isbn VARCHAR(17) NOT NULL UNIQUE
);

CREATE TABLE laptop_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    serial_number VARCHAR(80) NOT NULL UNIQUE
);
~~~

Sơ đồ:

~~~text
              book_assets                laptop_assets
         +-------------------+      +-----------------------+
         | id PK             |      | id PK                 |
         | asset_code UNIQUE |      | asset_code UNIQUE     |
         | display_name      |      | display_name          |
         | isbn NOT NULL     |      | serial_number NOT NULL|
         +-------------------+      +-----------------------+

              Không có bảng assets chung
~~~

Dữ liệu sách chỉ nằm trong `book_assets`, laptop chỉ nằm trong `laptop_assets`. Vì vậy các cột riêng của mỗi subtype có thể `NOT NULL` trực tiếp, tương tự `JOINED`.

### 6.3. UNIQUE của thuộc tính chung trở thành vấn đề liên bảng

Nếu cả hai bảng đều có:

~~~sql
UNIQUE (asset_code)
~~~

thì database bảo đảm:

- Không có hai sách cùng mã `asset_code`.
- Không có hai laptop cùng mã `asset_code`.

Nhưng **chưa bảo đảm** một sách và một laptop không có cùng mã:

~~~text
book_assets.asset_code   = "A-001"
laptop_assets.asset_code = "A-001"

Cả hai bảng riêng lẻ vẫn có thể thỏa UNIQUE.
~~~

Nếu yêu cầu là **duy nhất trên toàn hierarchy**, UNIQUE cục bộ trên từng bảng không đủ. Những giải pháp cấu trúc có thể gồm:

- Chuyển sang `SINGLE_TABLE` hoặc `JOINED` để có bảng chứa khóa chung.
- Tạo bảng đăng ký mã tài sản với constraint `UNIQUE(asset_code)` và quản lý tham chiếu nhất quán đến từng subtype.
- Dùng cơ chế DB phù hợp để bảo vệ tính duy nhất liên bảng, đồng thời xử lý concurrency đúng cách.

**Không chỉ dùng “SELECT xem mã có tồn tại chưa rồi INSERT”.** Hai transaction đồng thời có thể cùng vượt qua bước kiểm tra, dẫn đến mã trùng trên hai bảng khi không có ràng buộc toàn cục.

### 6.4. Primary key trong TABLE_PER_CLASS

Mỗi bảng concrete có PK riêng, nhưng khi Hibernate thực hiện truy vấn hoặc quản lý entity qua kiểu cha `Asset`, ID phải được dùng theo chiến lược nhất quán. Shared sequence giúp các subtype không vô tình nhận cùng giá trị ID chỉ vì mỗi bảng tự tăng từ 1.

Ví dụ:

~~~text
book_assets.id   = 1001
laptop_assets.id = 1002
book_assets.id   = 1003
~~~

Nếu mỗi bảng dùng independent identity và cả hai cùng có `id = 1`, việc diễn giải danh tính đa hình theo entity hierarchy trở nên không phù hợp với kỳ vọng của Hibernate cho `TABLE_PER_CLASS`.

### 6.5. FK đến lớp cha trừu tượng trở nên khó

Giả sử bảng `maintenance_records` cần tham chiếu đến **một tài sản bất kỳ**, sách hoặc laptop:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "asset_id")
private Asset asset;
~~~

Với `SINGLE_TABLE`, có một bảng `assets` để FK trỏ vào. Với `JOINED` cũng có bảng `assets` chung. Nhưng với `TABLE_PER_CLASS`, **không có một bảng gốc chung chứa mọi ID**. Một FK SQL thông thường không thể viết:

~~~sql
-- Không phải cú pháp foreign key hợp lệ:
FOREIGN KEY (asset_id)
REFERENCES (book_assets OR laptop_assets)(id);
~~~

Hibernate có thể diễn giải quan hệ đa hình bằng cơ chế riêng hoặc lựa chọn mapping khác tùy tình huống, nhưng database không có một FK chuẩn trực tiếp đến “union của nhiều bảng”. Nếu toàn vẹn tham chiếu đến mọi subtype là yêu cầu quan trọng, `TABLE_PER_CLASS` có thể không phù hợp với schema đó.

Giải pháp rõ ràng thường là dùng bảng khóa chung (`JOINED` hoặc `SINGLE_TABLE`), hoặc thiết kế lại các quan hệ và quy tắc tham chiếu. Không nên sử dụng một `asset_id` không có FK rồi mặc nhiên coi rằng JPA sẽ bảo vệ dữ liệu ngay cả khi SQL bên ngoài ghi.

### 6.6. Truy vấn đa hình

Một truy vấn:

~~~java
List<Asset> assets = em.createQuery(
    "select a from Asset a", Asset.class
).getResultList();
~~~

với `TABLE_PER_CLASS` thường được triển khai bằng dạng `UNION`/`UNION ALL` giữa các bảng concrete, tùy phiên bản, dialect và kiểu truy vấn. Điều đó ảnh hưởng đến kế hoạch truy vấn, index và khả năng áp dụng điều kiện/lấy trang.

Đây cũng là hệ quả của việc không có bảng cha chung. Ngay cả khi các subtype lưu những trường bắt buộc rất thuận tiện, truy vấn toàn hệ phân cấp và ràng buộc tham chiếu chung thường phức tạp hơn.

## 7. @MappedSuperclass: kế thừa mapping nhưng không tạo entity hierarchy

`@MappedSuperclass` có thể trông giống `TABLE_PER_CLASS` vì các field được kế thừa xuống nhiều bảng, nhưng nó có ý nghĩa **khác**.

Ví dụ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.SequenceGenerator;

@MappedSuperclass
public abstract class IdentifiedAsset {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "asset_seq")
    @SequenceGenerator(
        name = "asset_seq",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, length = 40)
    private String assetCode;

    protected IdentifiedAsset() {}

    protected IdentifiedAsset(String assetCode) {
        this.assetCode = assetCode;
    }
}
~~~

Các entity độc lập kế thừa mapping:

~~~java
@Entity
@Table(name = "book_assets")
public class BookAsset extends IdentifiedAsset {
    @Column(name = "isbn", nullable = false, unique = true)
    private String isbn;

    protected BookAsset() {}
}
~~~

~~~java
@Entity
@Table(name = "laptop_assets")
public class LaptopAsset extends IdentifiedAsset {
    @Column(name = "serial_number", nullable = false, unique = true)
    private String serialNumber;

    protected LaptopAsset() {}
}
~~~

Các bảng có PK và `asset_code` riêng. Nhưng:

- `IdentifiedAsset` **không phải entity** nên không truy vấn `select a from IdentifiedAsset a` theo nghĩa entity inheritance chuẩn.
- Không có một entity root chung để dùng trực tiếp với `EntityManager.find(IdentifiedAsset.class, id)`.
- Không thể lập một `@ManyToOne` chuẩn trỏ đến một entity `IdentifiedAsset` vì lớp đó không phải thực thể được quản lý.
- `UNIQUE(asset_code)` ở các bảng con chỉ có phạm vi từng bảng nếu không tạo một cấu trúc chung.
- Các mapping như `@Column`/`@Id` được kế thừa để tái sử dụng, nhưng không tạo bảng cha và không tạo polymorphic SQL hierarchy như `@Inheritance(TABLE_PER_CLASS)`.

Vì vậy, **`@MappedSuperclass` phù hợp để tái sử dụng mapping**, còn `@Inheritance` phù hợp khi muốn mô hình entity đa hình. Không chọn `@MappedSuperclass` chỉ để né việc quản lý PK và FK của một hierarchy thực sự.

### Có thể override mapping kế thừa không?

Một entity kế thừa từ mapped superclass có thể cần đổi tên cột. Jakarta Persistence hỗ trợ `@AttributeOverride` cho thuộc tính cơ bản:

~~~java
@Entity
@Table(name = "book_assets")
@AttributeOverride(
    name = "assetCode",
    column = @Column(
        name = "book_code",
        nullable = false,
        length = 40
    )
)
public class BookAsset extends IdentifiedAsset {
    // ...
}
~~~

Trong tình huống này, `name = "assetCode"` là tên thuộc tính Java ở mapped superclass, còn `@Column(name = "book_code")` là tên cột SQL. Việc override mapping **không tự tạo unique constraint toàn cục**; cần định nghĩa constraint theo yêu cầu và schema tương ứng.

Lưu ý không áp dụng override một cách máy móc cho entity inheritance khác chiến lược: những thuộc tính chung ở root entity có phạm vi mapping khác với thuộc tính kế thừa từ `@MappedSuperclass`.

## 8. Tổng hợp về primary key và sinh định danh

| Phương án | PK vật lý | Cách bảo đảm danh tính phù hợp |
|---|---|---|
| `SINGLE_TABLE` | Một PK ở `assets` | Generator của hierarchy cấp ID cho bảng chung |
| `JOINED` | PK ở `assets`; PK bảng con đồng thời là FK | ID do root xác định, bảng con dùng chính ID đó |
| `TABLE_PER_CLASS` | PK ở mỗi bảng concrete | Cần generator phù hợp cho toàn hierarchy, thường là shared sequence |
| `@MappedSuperclass` | PK độc lập ở mỗi bảng entity con | Kế thừa khai báo ID, nhưng không có identity/polymorphic root chung |

### 8.1. Không khai báo ID trùng trong subclass

Với `@Entity` root đã có:

~~~java
@Id
private Long id;
~~~

không nên thêm một `@Id private Long bookId;` độc lập trong `BookAsset` rồi kỳ vọng Hibernate tự coi đây là khóa riêng bảng con. Một hierarchy entity có quy tắc định danh chung; mapping ID tùy chiến lược phải được xác định nhất quán ở root hoặc theo hình thức JPA cho phép.

Với `JOINED`, `@PrimaryKeyJoinColumn` không tạo ID domain mới; nó xác định cột của bảng con dùng để join đến PK bảng cha.

### 8.2. Kiểm tra ID generator khi chuyển chiến lược

Nếu ứng dụng ban đầu dùng `GenerationType.IDENTITY` trong một bảng `SINGLE_TABLE`, việc chuyển sang `TABLE_PER_CLASS` có thể buộc đổi sang sequence hoặc generator phù hợp. Đổi generator cần quan tâm đến:

- Dải ID đã cấp và khả năng trùng với dữ liệu hiện tại.
- Sequence start value và allocation size.
- Nhiều node ứng dụng cấp ID đồng thời.
- Dữ liệu liên kết từ bảng khác đang dùng các ID cũ.
- Cách Hibernate cache hoặc cấp ID trước insert.

Không làm migration chỉ bằng cách sửa `@Inheritance` rồi để bảng, FK và generator cũ nguyên trạng.

### 8.3. Khóa tổng hợp thì sao?

Các hierarchy có định danh phức hợp cần tuân theo quy tắc JPA cho `@EmbeddedId` hoặc `@IdClass`. `JOINED` phải join các cột khóa tương ứng giữa bảng con và bảng cha; `TABLE_PER_CLASS` vẫn phải bảo đảm danh tính đa hình phù hợp với provider. Không thể tự ý cho mỗi subtype định nghĩa một cấu trúc primary key không tương thích rồi mong Hibernate truy vấn chúng như một hierarchy thống nhất.

Nếu nghiệp vụ buộc mỗi subtype có định danh hoàn toàn khác nhau, hãy cân nhắc liệu quan hệ Java inheritance có thật sự nên trở thành **entity inheritance** hay cần composition hoặc các entity độc lập.
## 9. Unique constraint: “duy nhất” trong phạm vi nào?

Một annotation `unique = true` có vẻ đơn giản, nhưng **phạm vi ràng buộc là bảng vật lý có chứa cột**. Để thiết kế kế thừa đúng, phải nói rõ giá trị cần duy nhất:

1. Trên mọi asset trong hệ phân cấp?
2. Chỉ trên các sách?
3. Chỉ trong một tenant?
4. Trên từng cặp nhiều cột?
5. Trên các subtype khác nhau nhưng chỉ khi chúng thuộc một trạng thái nhất định?

### 9.1. Unique của thuộc tính chung

Với `Asset.assetCode`, yêu cầu là một mã không được trùng giữa BookAsset và LaptopAsset.

- **`SINGLE_TABLE`:** `UNIQUE(assets.asset_code)` bao phủ tất cả hàng.
- **`JOINED`:** `UNIQUE(assets.asset_code)` bao phủ tất cả asset qua bảng cha.
- **`TABLE_PER_CLASS`:** `UNIQUE(book_assets.asset_code)` và `UNIQUE(laptop_assets.asset_code)` không ngăn trùng *giữa hai bảng*.
- **`@MappedSuperclass`:** cũng không có một constraint chung nếu không thiết kế thêm bảng đăng ký hoặc cấu trúc liên bảng.

Nếu mã chỉ cần duy nhất trong **mỗi tenant**, không nên đặt unique toàn cột khi nghiệp vụ cho phép hai tenant dùng cùng một mã. Ví dụ, với `tenant_id` là thuộc tính chung, `SINGLE_TABLE` hoặc `JOINED` có thể khai báo constraint kết hợp:

~~~java
@Entity
@Table(
    name = "assets",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_assets_tenant_code",
        columnNames = {"tenant_id", "asset_code"}
    )
)
public abstract class Asset {
    // @Id, các thuộc tính kế thừa khác ...

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "asset_code", nullable = false, length = 40)
    private String assetCode;
}
~~~

Nếu đã chọn unique kết hợp theo tenant, **không đồng thời thêm `unique = true` riêng cho `assetCode`** nếu điều đó cấm cùng mã xuất hiện ở hai tenant. Tên cột trong `columnNames` là tên cột SQL theo mapping, không phải tên field `tenantId`/`assetCode`.

Với `TABLE_PER_CLASS`, khai báo tương tự trên từng concrete table vẫn chỉ kiểm tra trong mỗi bảng; không tạo ràng buộc duy nhất toàn hierarchy của một tenant.

### 9.2. Unique của thuộc tính riêng subtype

`BookAsset.isbn` chỉ cần duy nhất giữa các sách:

- `SINGLE_TABLE`: có thể dùng unique trên `isbn` nếu nullable semantics của DB phù hợp, hoặc partial unique index dành cho `asset_kind = 'BOOK'`.
- `JOINED`: `UNIQUE(book_assets.isbn)` là tự nhiên.
- `TABLE_PER_CLASS`: `UNIQUE(book_assets.isbn)` là tự nhiên.

Nếu hai subtype độc lập đều có thuộc tính tên `registrationCode` nhưng nghiệp vụ muốn các mã không trùng nhau **kể cả khác subtype**, hãy đưa thuộc tính đó về cấp chung nếu nó thực sự cùng ý nghĩa và dùng mô hình có nơi áp đặt uniqueness chung. Không thể kỳ vọng hai unique constraints độc lập trên hai bảng tạo nên một unique constraint tổng hợp liên bảng.

### 9.3. Unique không thay thế kiểm soát đồng thời

Kiểm tra trước khi tạo entity:

~~~java
boolean exists = em.createQuery(
        "select count(a) from Asset a where a.assetCode = :code",
        Long.class)
    .setParameter("code", requestedCode)
    .getSingleResult() > 0;

if (!exists) {
    em.persist(new BookAsset(requestedCode, "Java", "978..."));
}
~~~

không đủ chống race condition: hai transaction có thể cùng thấy `exists = false`, rồi cùng insert. Cần unique constraint ở DB đúng phạm vi và xử lý lỗi khi constraint bị vi phạm.

Với `TABLE_PER_CLASS`, truy vấn đa hình có thể thấy mã trên nhiều bảng, nhưng vẫn không biến phép kiểm tra thành thao tác nguyên tử. Nếu global uniqueness là bất biến quan trọng, cần cấu trúc DB có thể thực thi nó.

## 10. Quan hệ đến lớp cha và lớp con: FK thực sự trỏ tới đâu?

Ngoài khóa của chính entity, inheritance ảnh hưởng đến **các entity khác tham chiếu đến hierarchy**.

Giả sử lịch bảo trì có thể liên quan đến một loại tài sản bất kỳ:

~~~java
@Entity
@Table(name = "maintenance_records")
public class MaintenanceRecord {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "asset_id", nullable = false)
    private Asset asset;

    protected MaintenanceRecord() {}
}
~~~

### 10.1. Tham chiếu đa hình đến Asset

Với `SINGLE_TABLE`:

~~~sql
FOREIGN KEY (asset_id) REFERENCES assets(id)
~~~

là FK đến bảng duy nhất của hierarchy.

Với `JOINED`, FK có thể trỏ đến `assets(id)` ở bảng cha; bảng này chứa một row chung cho mỗi asset, vì vậy quan hệ không cần biết subtype khi kiểm tra existence.

Với `TABLE_PER_CLASS`, không có bảng `assets` chung để FK trỏ tới. Một FK đơn cột tiêu chuẩn không thể tham chiếu “tổng hợp mọi bảng subtype”. Nếu nghiệp vụ cần ràng buộc tham chiếu chặt tới `Asset` nói chung, hãy cân nhắc lựa chọn chiến lược khác hoặc thiết kế bảng identity/registry riêng.

### 10.2. Tham chiếu chỉ đến BookAsset

Một review chỉ dành cho sách:

~~~java
@Entity
@Table(name = "book_reviews")
public class BookReview {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "book_id", nullable = false)
    private BookAsset book;

    protected BookReview() {}
}
~~~

Tùy chiến lược:

- **`JOINED`:** FK đến `book_assets(id)` có thể đồng thời bảo đảm đối tượng đích thực sự có hàng subtype sách. Đây là một lợi thế về ràng buộc vật lý.
- **`TABLE_PER_CLASS`:** FK đến `book_assets(id)` cũng có thể xác nhận subtype sách, vì bảng sách tồn tại riêng.
- **`SINGLE_TABLE`:** cột `book_id` thường chỉ có thể FK trực tiếp đến `assets(id)`. FK đó bảo đảm ID tồn tại nhưng **không tự bảo đảm `asset_kind = 'BOOK'`**.

Một quan hệ Java có target type `BookAsset` giúp Hibernate làm việc theo mapping đúng, nhưng không tự biến một FK SQL trỏ bảng chung thành “FK chỉ tới hàng có discriminator BOOK”. Nếu các dịch vụ khác cùng ghi dữ liệu và yêu cầu bảo vệ subtype tại DB, cần cơ chế ràng buộc bổ sung, ví dụ mô hình khóa kết hợp có discriminator được thiết kế đúng, trigger hoặc cấu trúc schema khác.

### 10.3. Khi root abstract vẫn có hàng trong bảng cha

Với `JOINED`, Java `abstract class Asset` không cho khởi tạo `new Asset()`, nhưng database có thể vẫn cho phép insert trực tiếp vào `assets` mà không insert vào `book_assets` hoặc `laptop_assets`. Một FK đến `assets(id)` chỉ xác nhận hàng cha tồn tại.

Do đó, abstract trong Java **không thay thế** constraint yêu cầu một hàng cha phải thuộc chính xác một subtype nếu database cần bảo đảm điều đó bất kể đường ghi.

## 11. “Bắt buộc” gồm những ý nghĩa khác nhau

Trong kế thừa, dễ nhầm bốn mức độ bắt buộc:

| Ý nghĩa | Ví dụ | Cơ chế |
|---|---|---|
| Thuộc tính phải có trong constructor/business operation | BookAsset luôn cần ISBN | Constructor, factory, domain service |
| Giá trị phải hợp lệ khi validation chạy | ISBN không null, không chỉ có khoảng trắng | Jakarta Bean Validation như `@NotBlank` |
| Mapping mô tả giá trị không tùy chọn | `@Basic(optional = false)`, `@Column(nullable = false)` | Metadata JPA/provider |
| DB không cho lưu hàng vi phạm | `NOT NULL`, `CHECK` | DDL thực tế |

### 11.1. @Basic(optional = false) không phải một CHECK theo subtype

JPA cho phép đánh dấu basic attribute không tùy chọn:

~~~java
@Basic(optional = false)
@Column(name = "isbn")
private String isbn;
~~~

Nhưng trong hierarchy `SINGLE_TABLE`, vấn đề vẫn là cột `isbn` được chia sẻ cho các hàng không phải sách. Nếu provider dùng thông tin `optional = false` để sinh hoặc kiểm tra nullability cột, kết quả có thể mâu thuẫn với chiến lược một bảng.

Do đó, với trường chỉ bắt buộc ở một subtype, nên biểu diễn nghiệp vụ bằng constructor/validation phù hợp, và dùng `CHECK` có điều kiện tại DB khi cần bảo vệ bất biến vật lý. `@Basic(optional = false)` hoặc `@Column(nullable = false)` không có khả năng tự diễn tả “chỉ NOT NULL khi discriminator là BOOK”.

### 11.2. @NotBlank, @NotNull và @Size

Với giá trị chuỗi:

~~~java
@NotBlank
@Size(max = 17)
private String isbn;
~~~

`@NotBlank` xác nhận không null và không chỉ gồm khoảng trắng khi Bean Validation được gọi. `@Size(max = 17)` giới hạn độ dài ở tầng validation. Chúng có phạm vi khác với `@Column(length = 17)` là metadata của schema.

Đối với kiểu số hoặc tham chiếu object, có thể dùng `@NotNull` cùng các constraint thích hợp. Những annotation validation yêu cầu dependency/provider và luồng validation phù hợp; không giả định mọi thao tác SQL ngoài ORM đều đi qua validation.

Nếu tích hợp Hibernate Validator với Hibernate ORM và bật các tính năng liên hệ giữa validation với schema generation, cần kiểm tra kết quả schema của `SINGLE_TABLE` để tránh DDL `NOT NULL` sai phạm vi. Với ràng buộc quan trọng, giữ migration database có chủ đích.

### 11.3. Không dựa vào primitive Java để thay constraint

Một field `int warrantyMonths` không thể null ở Java, nhưng có thể nhận 0 và 0 chưa chắc hợp lệ. Khi một subtype chỉ áp dụng số tháng bảo hành, `int` không tự đảm bảo DB có `CHECK(warranty_months > 0)` hoặc điều kiện theo loại.

Ví dụ conditional CHECK trong `SINGLE_TABLE`:

~~~sql
ALTER TABLE assets
ADD CONSTRAINT ck_laptop_warranty CHECK (
    asset_kind <> 'LAPTOP'
    OR (warranty_months IS NOT NULL AND warranty_months > 0)
);
~~~

Đây là một ví dụ khi logic subtype không chỉ là NOT NULL mà còn có miền giá trị hợp lệ. Nếu hệ thống muốn các loại không phải laptop luôn có `warranty_months = NULL`, cần thêm điều kiện tương ứng thay vì giả định CHECK trên tự quy định điều đó.

### 11.4. Field chung ở lớp cha có thể bắt buộc cho mọi subclass

Trong `SINGLE_TABLE` và `JOINED`, `Asset.assetCode` nằm ở bảng chung, nên `NOT NULL` áp dụng thống nhất. Với `TABLE_PER_CLASS`, mỗi bảng concrete cần constraint tương ứng. Trong `@MappedSuperclass`, các entity độc lập cũng cần constraint riêng tại từng bảng.

Nếu nghiệp vụ thay đổi để chỉ BookAsset phải có `assetCode`, đó không còn là bất biến chung đơn giản. Cần cân nhắc đặt thuộc tính vào subtype hoặc thiết kế một cách biểu diễn có điều kiện theo loại; vị trí trong Java hierarchy ảnh hưởng trực tiếp đến việc áp dụng constraint.

## 12. Discriminator và dữ liệu hợp lệ của SINGLE_TABLE

`@DiscriminatorColumn` thường được dùng để cho Hibernate biết mỗi hàng thuộc subtype nào:

~~~java
@DiscriminatorColumn(
    name = "asset_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 12
)
~~~

Subtype:

~~~java
@DiscriminatorValue("BOOK")
public class BookAsset extends Asset { /* ... */ }

@DiscriminatorValue("LAPTOP")
public class LaptopAsset extends Asset { /* ... */ }
~~~

### 12.1. Vì sao discriminator là yếu tố của ràng buộc?

Trong `SINGLE_TABLE`, một cột như `isbn` chỉ bắt buộc khi `asset_kind = 'BOOK'`. Vậy một CHECK dựa trên discriminator phải nhất quán với các giá trị `@DiscriminatorValue` trong Java.

Nếu đổi `@DiscriminatorValue("BOOK")` thành `@DiscriminatorValue("BOOK_ITEM")` mà không migration dữ liệu và CHECK, Hibernate có thể không nhận diện những hàng cũ hoặc database từ chối hàng mới.

**Discriminator vừa là metadata ORM vừa là một phần của hợp đồng dữ liệu** khi schema sử dụng nó để bảo vệ ràng buộc theo subtype.

### 12.2. Không mặc định discriminator đủ kiểm soát dữ liệu

Nếu ứng dụng không có database CHECK hoặc giới hạn giá trị discriminator, một script SQL có thể tạo:

~~~text
asset_kind = BOOK
isbn       = NULL
serial_number = SN-123
~~~

Bản ghi như vậy vi phạm mô hình BookAsset, dù có cột `asset_kind`. Hibernate có thể gặp lỗi khi đọc hoặc hoạt động không đúng kỳ vọng; chỉ có discriminator không tự mang toàn bộ constraint của subclass vào database.

Tương tự, một giá trị discriminator chưa biết có thể khiến provider không chọn được entity subtype phù hợp. Nếu hệ thống cho phép nhiều loại phát triển theo thời gian, kế hoạch migration và tính tương thích giữa phiên bản ứng dụng và DB là thiết yếu.

### 12.3. JOINED có nhất thiết cần discriminator không?

Không phải mọi mapping `JOINED` đều cần cột discriminator tường minh. Provider có thể suy ra subtype qua những bảng được join, tùy mapping/implementation. Nếu ứng dụng khai báo thêm discriminator trên root, phải quản lý sự nhất quán giữa giá trị discriminator và hàng subtype; đó là một ràng buộc nữa khi SQL bên ngoài ORM ghi dữ liệu.

Với `TABLE_PER_CLASS`, mỗi bảng concrete thể hiện một subtype nên polymorphic query thường dựa vào sự kết hợp các bảng, không giống điều kiện discriminator trong một bảng chung.

## 13. Thuộc tính @Version và các khóa liên quan đến concurrency

Một entity hierarchy có thể dùng optimistic locking:

~~~java
@Version
@Column(name = "record_version", nullable = false)
private long version;
~~~

Với trường `version` được khai báo ở root:

- `SINGLE_TABLE`: cột version nằm trong bảng `assets` chung.
- `JOINED`: version của entity hierarchy thường nằm trong bảng gốc `assets`, nơi có hàng định danh chung.
- `TABLE_PER_CLASS`: mapping kế thừa xuống từng bảng concrete, nên mỗi bảng lưu version của entity thuộc bảng đó.

`@Version` phục vụ phát hiện xung đột cập nhật; nó **không phải** foreign key, discriminator, và không thay thế `UNIQUE(assetCode)` hay `CHECK` theo subtype.

Nếu nhiều transaction cùng cập nhật cùng một entity, Hibernate có thể dùng version trong điều kiện update để phát hiện dữ liệu đã bị sửa. Tuy nhiên, tính duy nhất trên nhiều bảng (`TABLE_PER_CLASS`) vẫn phải được bảo vệ riêng; optimistic locking của một entity không tự khóa mọi bảng subtype khác.

## 14. Chuyển chiến lược kế thừa là migration dữ liệu, không chỉ sửa annotation

Khi chuyển chiến lược, cần chuyển cả dữ liệu, ID, ràng buộc và FK. Ví dụ hệ thống đang dùng `SINGLE_TABLE` và muốn sang `JOINED` vì có nhiều trường riêng cần `NOT NULL`.

### 14.1. Từ SINGLE_TABLE sang JOINED

Dữ liệu ban đầu:

~~~text
assets(id, asset_kind, asset_code, display_name, isbn, serial_number)
~~~

Dữ liệu sau migration dự kiến:

~~~text
assets(id, asset_code, display_name)
book_assets(id, isbn)
laptop_assets(id, serial_number)
~~~

Các bước thiết kế dữ liệu thường gồm:

1. Xác định khóa `id` và mọi bảng đang tham chiếu `assets(id)`.
2. Tạo bảng con với PK/FK dùng ID của bảng gốc.
3. Sao chép ISBN của các hàng BOOK sang `book_assets` theo cùng ID.
4. Sao chép serial number của LAPTOP sang `laptop_assets` theo cùng ID.
5. Xử lý các hàng có discriminator/field không hợp lệ trước khi áp `NOT NULL` và unique.
6. Đảm bảo các đường đọc và ghi không bị lệch cấu trúc khi triển khai phiên bản ứng dụng mới.
7. Sau khi dữ liệu và ứng dụng tương thích, mới loại bỏ các cột subtype khỏi bảng gốc nếu đúng kế hoạch.

Nếu thực hiện việc copy mà không giữ ID, các FK đang trỏ đến asset có thể mất tính đúng đắn. Chuyển dữ liệu trong phạm vi transaction/migration thích hợp, cân nhắc khóa, thời gian bảo trì và khả năng rollback.

### 14.2. Từ JOINED sang SINGLE_TABLE

Cần join dữ liệu từ bảng gốc sang các bảng subtype và đưa cột riêng vào bảng chung. Những cột chỉ áp dụng cho một subtype phải **nullable ở mức cột vật lý** và có thể thêm `CHECK` theo discriminator để giữ ràng buộc subtype.

Các trường hợp cần xử lý:

- Hàng cha không có hàng subtype.
- Một hàng cha xuất hiện ở nhiều bảng subtype.
- Giá trị bắt buộc bị thiếu.
- Mã loại không khớp với subtype.
- Tên cột trùng giữa nhiều subclass có ý nghĩa khác nhau.
- Những bảng ngoài hierarchy đang FK tới bảng con; chuyển sang chung có thể mất khả năng FK chỉ đến một subtype.

### 14.3. Từ hai chiến lược có bảng cha sang TABLE_PER_CLASS

Cần nhân các cột chung xuống từng bảng, chuyển dữ liệu, và đặc biệt thiết kế lại:

- Generator ID dùng chung và khả năng trùng ID giữa subtype.
- Unique constraint toàn hierarchy, ví dụ `assetCode`.
- Bảng khác đang FK tới `assets(id)`.
- Truy vấn report/SQL trực tiếp dựa vào bảng cha.
- Những hệ thống tích hợp đồng bộ dữ liệu và auditing.

Có thể thấy `TABLE_PER_CLASS` thuận tiện cho thuộc tính subtype bắt buộc nhưng lại gây khó ở **identity và referential integrity cấp hierarchy**. Vì vậy việc chọn chiến lược phải dựa trên bất biến dữ liệu dài hạn, không chỉ dựa vào số cột null nhìn thấy ở DB.
## 15. Cách chọn chiến lược từ yêu cầu ràng buộc

Để lựa chọn, hãy bắt đầu từ **bất biến dữ liệu** và hình thức truy vấn, thay vì chọn chiến lược chỉ vì code Java có `extends`.

### 15.1. Khi nào SINGLE_TABLE phù hợp?

`SINGLE_TABLE` thường có lợi khi:

- Cần nhiều truy vấn tới toàn bộ `Asset` theo kiểu đa hình.
- Cần FK từ bảng khác trỏ đến một tài sản bất kỳ.
- Có nhiều thuộc tính chung cần `NOT NULL`, `UNIQUE` trên toàn hierarchy.
- Số thuộc tính riêng subtype vừa phải.
- Nhóm có thể quản lý validation và `CHECK` có điều kiện cho thuộc tính riêng bắt buộc.

Ví dụ hệ thống có hàng triệu asset và thường tìm theo `assetCode` không phân biệt loại. Một bảng chung với unique index trên `asset_code` diễn đạt quy tắc đơn giản.

Nhược điểm lớn liên quan trực tiếp bài học là **không thể tạo NOT NULL toàn cột cho mỗi thuộc tính chỉ thuộc một subtype** khi các subtype khác cần giá trị null. Muốn DB bảo vệ quy tắc đó phải thiết kế CHECK có điều kiện hoặc một cơ chế tương đương.

### 15.2. Khi nào JOINED phù hợp?

`JOINED` thường phù hợp khi:

- Thuộc tính riêng của subtype nhiều và có ràng buộc bắt buộc rõ.
- Vẫn cần FK và unique constraint chung cho `Asset`.
- Muốn schema chuẩn hóa phần chung và riêng qua PK/FK.
- Chấp nhận các join bổ sung khi tải entity đầy đủ hoặc truy vấn đa hình.

Ví dụ `BookAsset.isbn` được đặt `NOT NULL UNIQUE` trong bảng `book_assets` và `LaptopAsset.serialNumber` trong `laptop_assets`. Đồng thời, mã `assetCode` vẫn unique ở bảng `assets`.

Điểm cần xem xét là DB FK từ bảng con đến bảng cha **không tự chứng minh mọi row cha có đúng một row ở một subtype**, đặc biệt khi có SQL bên ngoài ORM. Nếu đây là bất biến thiết yếu, phải thiết kế cách bảo vệ toàn vẹn bổ sung.

### 15.3. Khi nào TABLE_PER_CLASS phù hợp?

`TABLE_PER_CLASS` hợp lý hơn khi:

- Các subtype tương đối độc lập về dữ liệu.
- Truy vấn phần lớn nhắm vào một subtype cụ thể.
- Cột và ràng buộc của từng subtype cần tách hoàn toàn.
- Không phụ thuộc nhiều vào FK và uniqueness toàn hierarchy.
- Có thể dùng ID generator phù hợp cho toàn bộ hierarchy.

Ví dụ báo cáo chỉ truy vấn sách hoặc chỉ truy vấn laptop, và mã nghiệp vụ được phép trùng giữa hai nhóm. Khi đó mỗi bảng có thể giữ constraints riêng thuận tiện.

Ngược lại, nếu cần `maintenance_records.asset_id` tham chiếu mọi loại tài sản qua một FK chuẩn, hoặc cần `assetCode` unique toàn hierarchy, `TABLE_PER_CLASS` sẽ làm thiết kế phức tạp hơn đáng kể.

### 15.4. Khi nào nên dùng MappedSuperclass?

Nếu mục tiêu chỉ là tái sử dụng mapping như ID, `createdAt`, `updatedAt`, nhưng các entity con không cần truy vấn đa hình và không đại diện cùng một tập thực thể, `@MappedSuperclass` thường đơn giản hơn entity inheritance.

Tuy nhiên, đừng nhầm việc chia sẻ mã Java với việc chia sẻ một khóa hoặc constraint DB: **MappedSuperclass không tạo bảng cha để áp đặt ràng buộc chung**.

### 15.5. Một ma trận quyết định nhanh

| Yêu cầu mạnh nhất | Phương án thường dễ biểu diễn |
|---|---|
| Global unique của thuộc tính chung | `SINGLE_TABLE` hoặc `JOINED` |
| FK từ bảng khác đến mọi subtype | `SINGLE_TABLE` hoặc `JOINED` |
| Mỗi subtype có nhiều trường riêng `NOT NULL` | `JOINED` hoặc `TABLE_PER_CLASS` |
| Đọc đa hình thường xuyên, ít join | `SINGLE_TABLE` |
| Subtype độc lập và query riêng | Có thể xét `TABLE_PER_CLASS` |
| Muốn tái sử dụng metadata, không cần entity polymorphism | `@MappedSuperclass` |
| Bảng DB có cấu trúc đã tồn tại cố định | Chọn mapping khớp schema và migration, không chỉ theo lý thuyết |
| Có nhiều đường ghi SQL ngoài ORM | Ưu tiên constraint DB có thể diễn tả trực tiếp và theo dõi được |

Không có chiến lược nào luôn tốt hơn. Quyết định phải cân bằng **khả năng thực thi constraint**, **khả năng điều hướng/truy vấn đa hình**, **hiệu năng**, và **chi phí migration**.

## 16. Những lỗi thực tế khi triển khai inheritance

| Triệu chứng | Nguyên nhân có thể | Điều cần xem |
|---|---|---|
| Insert Laptop báo cột `isbn` không được null | Đặt `NOT NULL` toàn cột trong `SINGLE_TABLE` | Nullable vật lý và CHECK có điều kiện |
| Có hai asset cùng mã dù đã khai báo unique | Dùng `TABLE_PER_CLASS`/mapped superclass, unique riêng từng bảng | Nơi cần global unique và cấu trúc DB chung |
| Thêm BookAsset gây lỗi khóa chính trùng | Generator ID không phù hợp, nhất là `TABLE_PER_CLASS` | Shared sequence, dải ID và generation strategy |
| Child row tồn tại nhưng parent row thiếu | Không có FK bảng con → bảng cha hoặc dữ liệu bị sửa ngoài ORM | Constraint FK của `JOINED` |
| Parent row tồn tại nhưng không nhận diện được subtype | Thiếu hàng subclass hoặc discriminator không nhất quán | Schema JOINED/discriminator, dữ liệu lịch sử |
| Hibernate đọc không được entity có discriminator lạ | Dữ liệu `asset_kind` không tương ứng mapping hiện tại | Discriminator values và migration |
| `@NotBlank` có tác dụng ở service nhưng SQL trực tiếp vẫn ghi null | Validation Java không chạy trên SQL ngoài ORM | CHECK/NOT NULL thực ở DB |
| FK tới BookAsset vẫn tham chiếu được LaptopAsset | `SINGLE_TABLE` FK tới bảng chung không bảo vệ discriminator | Ràng buộc subtype hoặc đổi schema |
| @Column(unique=true) không sinh constraint sau deployment | Schema production quản lý bằng migration, ORM không thay đổi DDL | Migration và schema thật |
| Thay `@Inheritance` khiến truy vấn hoặc báo cáo sai | DB còn cấu trúc chiến lược cũ | Kế hoạch chuyển đổi bảng, SQL, FK |
| Truy vấn `Asset` chậm sau khi tách bảng | `JOINED` tăng join hoặc `TABLE_PER_CLASS` cần union | Truy vấn đa hình, index và execution plan |
| Xóa subclass bị lỗi FK | `JOINED` có ràng buộc child-to-parent, thứ tự xóa hoặc dữ liệu liên quan | Transaction, cascades, DDL constraints |
| Cùng một ID xuất hiện ở nhiều subtype | Generator cấp ID độc lập hoặc nhập dữ liệu ngoài ORM | Quy tắc identity của hierarchy, `TABLE_PER_CLASS` |
| CHECK từ chối subtype mới | Migration chưa bổ sung giá trị discriminator mới | CHECK condition và rollout version |
| Thuộc tính bắt buộc ở subclass lại chứa null | Chỉ có annotation/validation, không có DB rule phù hợp | Migration, validation, CHECK hoặc NOT NULL tùy strategy |

### 16.1. Đừng giải quyết lỗi NOT NULL bằng cách gỡ hết constraint

Giả sử đã triển khai `SINGLE_TABLE` và nhận lỗi khi thêm laptop vì `isbn NOT NULL`. Chỉ đổi cột `isbn` sang nullable giúp laptop được ghi, nhưng cũng khiến **sách thiếu ISBN** được database chấp nhận nếu không có biện pháp khác.

Cần xác định hai tầng:

1. Cột nullable để chấp nhận các hàng thuộc subtype khác.
2. Ràng buộc `CHECK` theo discriminator để yêu cầu ISBN đối với riêng BOOK.

Ở các môi trường chỉ ghi qua ứng dụng, có thể bắt đầu bằng validation theo subtype, nhưng với yêu cầu toàn vẹn nghiêm ngặt vẫn cần thiết kế DB constraint tương ứng.

### 16.2. Không thể “sửa UNIQUE toàn hierarchy” bằng hai unique index riêng

Với hai bảng trong `TABLE_PER_CLASS`, đặt thêm unique index trên `book_assets.asset_code` và `laptop_assets.asset_code` vẫn không bảo vệ các giá trị trùng xuyên bảng. Muốn giải quyết phải **thay đổi phạm vi dữ liệu được constraint nhìn thấy**, ví dụ dùng một bảng registry chung; không có annotation `unique = true` nào tự tạo cross-table uniqueness từ hai bảng riêng.

### 16.3. Không coi schema do Hibernate sinh là thay thế migration

Hibernate có thể hỗ trợ tạo hoặc kiểm tra schema cho môi trường phát triển. Nhưng những thay đổi như:

- Thêm bảng subtype trong `JOINED`.
- Chuyển thuộc tính sang bảng khác.
- Thêm partial unique index.
- Thêm `CHECK` conditional.
- Backfill cột mới bắt buộc.
- Chuyển ID generator hoặc sửa FK.

đều có thể đòi migration được thiết kế riêng. Chỉ sửa annotation rồi hy vọng Hibernate sẽ biến đổi dữ liệu cũ không phải chiến lược triển khai đáng tin cậy.

## 17. Tình huống thực hành

### Tình huống 1 — BOOK cần ISBN, LAPTOP không có ISBN

Các entity dùng `SINGLE_TABLE` và `BookAsset.isbn` được khai báo:

~~~java
@Column(nullable = false)
private String isbn;
~~~

**Câu hỏi:** vì sao có rủi ro khi Hibernate tạo DDL?

**Định hướng:** Cột `isbn` nằm trong một bảng chung, các hàng laptop cần null. Nếu DDL áp `NOT NULL` toàn cột, không thể thêm laptop. Dùng nullable ở mức cột và kiểm tra điều kiện khi `asset_kind = 'BOOK'` qua validation và DB CHECK thích hợp.

### Tình huống 2 — Cần mã duy nhất toàn hệ thống

Hai bảng `book_assets` và `laptop_assets` của `TABLE_PER_CLASS` đều có `UNIQUE(asset_code)`. Sách `A-001` đã tồn tại; có thêm laptop `A-001` được không?

**Định hướng:** Database có thể cho phép, vì unique nằm ở hai bảng khác nhau. Nếu nghiệp vụ cấm, cần một nơi quản lý uniqueness chung hoặc chọn chiến lược có bảng chung.

### Tình huống 3 — Khóa chính ở JOINED

Entity `Asset` có `@Id Long id`. `BookAsset` được lưu trong `book_assets`, có cột `id` là PK đồng thời FK về `assets.id`.

**Câu hỏi:** có cần khai báo một `@Id bookId` mới ở `BookAsset` không?

**Định hướng:** Không. Subclass kế thừa identity của root. `@PrimaryKeyJoinColumn` có thể xác định cách bảng con nối tới bảng cha; đó không phải một ID domain mới.

### Tình huống 4 — FK chỉ cho sách

Một bảng `book_reviews` phải tham chiếu đúng `BookAsset`, không được trỏ đến LaptopAsset. So sánh mức bảo vệ bằng FK của `SINGLE_TABLE` và `JOINED`.

**Định hướng:** Với `JOINED`, FK đến `book_assets(id)` có thể xác nhận tồn tại subtype sách. Với `SINGLE_TABLE`, FK tới `assets(id)` chỉ xác nhận có asset; cần cơ chế bổ sung để buộc discriminator BOOK nếu yêu cầu bảo vệ ở DB.

### Tình huống 5 — Root abstract nhưng SQL ngoài ORM ghi trực tiếp

Dự án dùng `JOINED`; một script insert hàng mới vào `assets` mà không tạo hàng trong `book_assets` hay `laptop_assets`.

**Câu hỏi:** FK từ bảng con về bảng cha có tự chặn hàng cha mồ côi về mặt subtype không?

**Định hướng:** Không. FK bảo vệ child phải có parent, không tự yêu cầu parent phải có một child. Java abstract cũng không ngăn script SQL tạo hàng bảng cha. Cần xem cơ chế kiểm soát dữ liệu ngoài ORM nếu invariant này quan trọng.

### Tình huống 6 — MappedSuperclass có query đa hình không?

~~~java
@MappedSuperclass
abstract class BaseRecord {
    @Id
    Long id;
}

@Entity
class BookRecord extends BaseRecord {}

@Entity
class LaptopRecord extends BaseRecord {}
~~~

**Câu hỏi:** dùng `select r from BaseRecord r` như một root entity đa hình có phù hợp không?

**Định hướng:** Không theo mapping chuẩn, vì `BaseRecord` không phải entity. Muốn query đa hình qua root được quản lý, phải thiết kế entity inheritance thích hợp hoặc query từng entity độc lập.

### Tình huống 7 — Chọn chiến lược

Một hệ thống có 8 subtype, mỗi subtype có 20 thuộc tính riêng phải `NOT NULL`. Hệ thống vẫn cần khóa `assetCode` unique chung và bảng `maintenance_records` FK tới mọi asset.

**Gợi ý:** `JOINED` thường là ứng viên đáng cân nhắc: trường riêng được `NOT NULL` trong bảng subtype, khóa và FK chung nằm ở root. Cần chấp nhận chi phí join, kiểm tra dữ liệu cha thiếu subtype và các query thường dùng.

### Tình huống 8 — Validation không thay thế schema

Ứng dụng dùng `@NotBlank` cho `BookAsset.isbn` và service không cho lưu sách rỗng. Một hệ thống ETL ghi trực tiếp hàng `BOOK` có `isbn = NULL`.

**Câu hỏi:** annotation validation có chắc ngăn được không?

**Định hướng:** Không. ETL không đi qua Bean Validation của ứng dụng. Cần CHECK/constraint DB phù hợp nếu tất cả nguồn ghi đều phải tuân theo quy tắc.

### Tình huống 9 — Đổi chiến lược đang chạy production

Ứng dụng muốn chuyển từ `SINGLE_TABLE` sang `JOINED` để giảm cột null. Có đủ nếu chỉ đổi `@Inheritance` và thêm `@Table` ở các subclass?

**Định hướng:** Không. Cần tạo bảng con, chuyển các giá trị, giữ nguyên ID và FK liên quan, xử lý dữ liệu vi phạm constraint, phối hợp rollout, cập nhật query/SQL ngoài ORM và chỉ xóa cột cũ khi dữ liệu đã tương thích.

## 18. Kết luận và điểm cần ghi nhớ

Sự khác biệt giữa các chiến lược kế thừa không dừng ở **số bảng**:

- **`SINGLE_TABLE`:** một PK và một nơi đặt unique constraint chung. Thuộc tính chỉ bắt buộc ở subtype cần validation/constraint **có điều kiện**, vì cột vật lý cũng được dùng cho những hàng thuộc subtype khác.
- **`JOINED`:** các bảng con dùng PK đồng thời làm FK đến bảng cha. Trường riêng được `NOT NULL` trực tiếp, còn unique/FK chung có thể đặt trên bảng cha. Tuy vậy, FK child-to-parent một mình chưa bảo vệ mọi invariant liên bảng.
- **`TABLE_PER_CLASS`:** mỗi concrete subtype có bảng, PK, constraint riêng. Trường subtype bắt buộc dễ diễn đạt nhưng **global uniqueness** và FK đa hình khó hơn vì không có bảng chung. Chọn ID generator tương thích cho hierarchy.
- **`@MappedSuperclass`:** tái sử dụng metadata cho các entity độc lập; không tạo entity root, bảng chung hay constraint toàn hierarchy.

Để đánh giá một hierarchy Hibernate, hãy lần lượt xác định **khóa chính nằm đâu**, **ai có quyền tham chiếu tới root/subtype bằng FK**, **UNIQUE bao phủ những hàng nào**, **NOT NULL áp dụng cho tất cả hàng hay chỉ một loại**, và **dữ liệu được bảo vệ ra sao khi ghi ngoài ORM**. Đây là các câu hỏi trực tiếp quyết định chiến lược kế thừa và thiết kế migration.

### Tài liệu đọc tiếp

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — đặc tả `@Inheritance`, `@MappedSuperclass`, `@DiscriminatorColumn`, `@PrimaryKeyJoinColumn` và mapping khóa.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn User Guide đúng phiên bản để tra mapping `SINGLE_TABLE`, `JOINED`, `TABLE_PER_CLASS`.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — các ví dụ entity inheritance, identifier và schema.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/) — các ràng buộc `@NotNull`, `@NotBlank`, `@Size`.
- [PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — `CHECK`, `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và các điểm cần lưu ý khi thiết kế schema.

> Code và DDL trong bài thể hiện mô hình JPA/Hibernate hiện đại. Việc sinh SQL cụ thể phụ thuộc Hibernate version, JDBC driver, dialect và schema migration. Khi triển khai với một database khác PostgreSQL, điều chỉnh cú pháp constraint, sequence và index theo khả năng thực tế của hệ quản trị đó.



