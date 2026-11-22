# Giới hạn định danh và ánh xạ trong hệ phân cấp JPA

Kế thừa trong Java cho phép các lớp con chia sẻ thuộc tính và hành vi của lớp cha. Khi những lớp đó là **entity JPA**, kế thừa còn đặt ra câu hỏi về **định danh bền vững**, **bảng và cột cơ sở dữ liệu**, **cách lưu thuộc tính riêng của từng lớp**, **truy vấn đa hình** và **ràng buộc toàn vẹn**.

Một thiết kế dễ mắc lỗi là xem mỗi subclass như một entity hoàn toàn độc lập về khóa chính, trong khi JPA đang quản lý chúng như các kiểu con trong **cùng một hệ phân cấp entity**. Ví dụ, `DigitalAsset` và `PhysicalAsset` cùng kế thừa entity `Asset`: mỗi đối tượng cần một định danh nhất quán trong hệ phân cấp, còn cách ID được lưu xuống các bảng tùy vào chiến lược `SINGLE_TABLE`, `JOINED` hay `TABLE_PER_CLASS`.

Bài học giải thích những **giới hạn và quy tắc** đó, đồng thời phân biệt **`@Entity` inheritance** với **`@MappedSuperclass`**. Mục tiêu không chỉ là nhớ annotation, mà còn hiểu hệ quả của việc chọn chiến lược ánh xạ đối với khóa chính, khóa ngoại, ràng buộc kiểu dữ liệu và truy vấn.

## 1. Hai tầng kế thừa: Java và ORM

Giả sử mô hình tài sản:

~~~text
                         Asset (entity)
                        id, assetCode
                        /           \
                       /             \
           DigitalAsset               PhysicalAsset
           downloadUrl                weightGrams
~~~

Ở tầng Java:

- `DigitalAsset extends Asset` nên kế thừa các trường/phương thức phù hợp của `Asset`.
- `PhysicalAsset extends Asset` cũng kế thừa ID và assetCode.
- Một biến kiểu `Asset` có thể tham chiếu tới object của một subclass.
- Java không quy định object đó được lưu ở bảng nào.

Ở tầng JPA:

- `Asset` là **root entity** của hệ phân cấp nếu nó được đánh dấu `@Entity` và không có superclass entity khác.
- `@Inheritance` trên root xác định chiến lược lưu hệ phân cấp.
- Mọi subtype entity sử dụng **định danh được khai báo trong root hierarchy**, không tạo một vòng đời ID tách biệt chỉ vì có class con.
- JPA có thể truy vấn root và nhận các concrete subtype bằng **truy vấn đa hình**.
- Database có thể lưu toàn bộ phân cấp trong một bảng, nhiều bảng nối bằng khóa hoặc nhiều bảng riêng, tùy chiến lược.

~~~text
              Java class hierarchy
                      |
           JPA inheritance metadata
                      |
       +--------------+--------------+
       |              |              |
   SINGLE_TABLE      JOINED      TABLE_PER_CLASS
       |              |              |
     1 bảng       root + các      bảng cho từng
    toàn hệ       bảng subtype     concrete entity
       |              |              |
       +--------------+--------------+
                      |
              Entity identity
       (mỗi đối tượng có một ID logic)
~~~

**Cần tách “một object có một ID” khỏi “ID xuất hiện tại bao nhiêu bảng”.** Trong `JOINED`, cùng giá trị ID có thể nằm ở bảng root và bảng subclass để liên kết một đối tượng duy nhất; đó không phải hai entity khác nhau.

## 2. Giới hạn quan trọng nhất: khóa chính thuộc về hệ phân cấp

### 2.1. Khai báo @Id ở root entity

Một cách thiết kế phổ biến:

~~~java
package com.example.assets.domain;

import jakarta.persistence.Column;
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
@Inheritance(strategy = InheritanceType.JOINED)
@SequenceGenerator(
    name = "asset_id_generator",
    sequenceName = "asset_id_seq",
    allocationSize = 1
)
public abstract class Asset {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "asset_id_generator"
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, length = 50)
    private String assetCode;

    protected Asset() {
    }

    protected Asset(String assetCode) {
        this.assetCode = assetCode;
    }

    public Long getId() {
        return id;
    }

    public String getAssetCode() {
        return assetCode;
    }
}
~~~

Subclass thứ nhất:

~~~java
package com.example.assets.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "digital_assets")
@PrimaryKeyJoinColumn(
    name = "asset_id",
    referencedColumnName = "id"
)
public class DigitalAsset extends Asset {

    @Column(name = "download_url", nullable = false, length = 500)
    private String downloadUrl;

    protected DigitalAsset() {
    }

    public DigitalAsset(String assetCode, String downloadUrl) {
        super(assetCode);
        this.downloadUrl = downloadUrl;
    }

    public String getDownloadUrl() {
        return downloadUrl;
    }
}
~~~

Subclass thứ hai:

~~~java
package com.example.assets.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "physical_assets")
@PrimaryKeyJoinColumn(
    name = "asset_id",
    referencedColumnName = "id"
)
public class PhysicalAsset extends Asset {

    @Column(name = "weight_grams", nullable = false)
    private Integer weightGrams;

    protected PhysicalAsset() {
    }

    public PhysicalAsset(String assetCode, Integer weightGrams) {
        super(assetCode);
        this.weightGrams = weightGrams;
    }

    public Integer getWeightGrams() {
        return weightGrams;
    }
}
~~~

Điểm cần lưu ý:

1. `Asset` chứa **một `@Id`** cùng cơ chế sinh khóa cho hierarchy.
2. `DigitalAsset` và `PhysicalAsset` **không khai báo thêm `@Id`** hoặc `@GeneratedValue`.
3. Dù là class `abstract`, `Asset` vẫn có thể là **entity** và là đối tượng của JPQL `FROM Asset`.
4. `@Inheritance(strategy = JOINED)` xác định cách map entity kế thừa, không thay đổi quy tắc Java `extends`.
5. `@PrimaryKeyJoinColumn` đổi tên cột PK/FK ở bảng subclass thành `asset_id`; không sinh một ID khác.

Ví dụ trên giả định database và provider hỗ trợ sequence. Với database không có sequence, cần chọn chiến lược tạo khóa tương thích, nhưng **vẫn dùng một quy tắc định danh thống nhất cho hierarchy**.

### 2.2. Vì sao không khai báo khóa riêng trong subclass?

Tránh cấu hình ý tưởng như sau:

~~~java
@Entity
public class WrongDigitalAsset extends Asset {

    // Không dùng trong entity subclass của hierarchy đã có @Id.
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long digitalId;
}
~~~

Nếu root đã định nghĩa `Asset.id` là primary key, việc thêm một `@Id` độc lập ở subclass sẽ trái với mô hình entity inheritance chuẩn: một đối tượng subtype không có đồng thời “ID của Asset” và một “primary key riêng của DigitalAsset” được JPA quản lý như hai định danh entity.

Nếu subclass cần một **mã nghiệp vụ riêng**, hãy dùng một thuộc tính thông thường có unique constraint khi cần:

~~~java
@Column(name = "license_code", unique = true)
private String licenseCode;
~~~

`licenseCode` có thể dùng để tra cứu nghiệp vụ, nhưng nó không thay thế identity do `@Id` của root quy định.

### 2.3. Một @Id không đồng nghĩa mọi bảng cùng có một cột tên id

Ví dụ `JOINED`:

~~~text
assets                digital_assets
+----------------+    +--------------------------+
| id (PK) = 41   |<---| asset_id (PK, FK) = 41   |
| asset_code     |    | download_url             |
+----------------+    +--------------------------+
~~~

Tên cột `assets.id` và `digital_assets.asset_id` khác nhau. Nhưng cả hai tham gia lưu **cùng một entity `DigitalAsset#41`**. Đây là vấn đề ánh xạ khóa ở SQL, không phải khai báo hai ID ở Java.

## 3. Quy tắc cơ bản của entity inheritance

Một vài quy tắc có ảnh hưởng trực tiếp tới thiết kế:

| Vấn đề | Nguyên tắc cần nhớ |
| --- | --- |
| Kế thừa trong Java | Entity subclass có thể kế thừa từ entity superclass theo hierarchy |
| Khóa chính | Được khai báo trong root entity hoặc được kế thừa từ mapped superclass |
| Generator khóa | Không cấu hình generator độc lập mâu thuẫn ở từng entity subtype |
| `@Inheritance` | Được khai báo trên root entity để chọn mapping hierarchy |
| `@Entity` ở subclass | Class con tham gia hierarchy khi được khai báo là entity |
| `@Table` | Ý nghĩa tùy chiến lược; SINGLE_TABLE không có bảng riêng cho mỗi subclass |
| Quan hệ JPA | Có thể khai báo ở root và được các subtype kế thừa theo mapping |
| Truy vấn root | Có thể trả các subclass entity thích hợp |
| `@MappedSuperclass` | Tái sử dụng mapping nhưng không tự là entity để `find` hoặc JPQL đa hình |
| Đổi primary key sau persist | Không phải thao tác cập nhật entity thông thường, cần tránh |

Trong JPA chuẩn, entity class phải đáp ứng ràng buộc về constructor, khả năng provider tạo/quản lý instance và class không được `final`. Đừng áp dụng bừa Java `record` hoặc một cấu trúc `final` làm entity subclass chỉ vì nó tiện biểu diễn data.

## 4. SINGLE_TABLE: toàn bộ hệ phân cấp dùng một bảng

### 4.1. Cách ánh xạ

Trên `Asset` thay chiến lược thành:

~~~java
@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "asset_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 20
)
public abstract class Asset {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    // Các thuộc tính chung...
}
~~~

Trên các subtype:

~~~java
@Entity
@DiscriminatorValue("DIGITAL")
public class DigitalAsset extends Asset {
    private String downloadUrl;
    // ...
}

@Entity
@DiscriminatorValue("PHYSICAL")
public class PhysicalAsset extends Asset {
    private Integer weightGrams;
    // ...
}
~~~

Đây là **biến thể thay thế mapping `JOINED` ở mục 2**. Khi dùng `SINGLE_TABLE`, không giữ `@PrimaryKeyJoinColumn` dành cho bảng subclass của ví dụ trước; các thuộc tính subtype được lưu trực tiếp trong **cùng bảng root**.

`@DiscriminatorColumn` và `@DiscriminatorValue` giúp provider phân biệt record nào tương ứng với entity subtype nào. Với discriminator kiểu chuỗi, cột `asset_kind` có thể chứa `DIGITAL` hoặc `PHYSICAL`.

### 4.2. Schema và một identity space trong bảng

~~~sql
CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_kind VARCHAR(20) NOT NULL,
    asset_code VARCHAR(50) NOT NULL,
    download_url VARCHAR(500),
    weight_grams INTEGER
);
~~~

Ví dụ dữ liệu:

| `id` | `asset_kind` | `asset_code` | `download_url` | `weight_grams` |
| ---: | --- | --- | --- | ---: |
| 41 | DIGITAL | DL-041 | /files/book.pdf | *NULL* |
| 42 | PHYSICAL | PHY-042 | *NULL* | 850 |
| 43 | DIGITAL | DL-043 | /files/course.zip | *NULL* |

**ID luôn duy nhất trong bảng `assets`**, bất kể record biểu diễn subtype nào. Không thể có cả `DigitalAsset#41` và `PhysicalAsset#41` dưới dạng hai hàng khác nhau trong cùng bảng với `id` là primary key.

### 4.3. Giới hạn NOT NULL với thuộc tính chỉ có ở subtype

`DigitalAsset.downloadUrl` có thể bắt buộc theo nghiệp vụ, nhưng các hàng `PHYSICAL` không có giá trị `download_url`.

Nếu đặt:

~~~sql
download_url VARCHAR(500) NOT NULL
~~~

cho toàn bộ bảng `assets`, bản ghi `PHYSICAL` có thể không thể được chèn, vì nó không có `download_url`.

Do đó, ở `SINGLE_TABLE`, những cột chỉ thuộc một subtype thường cần **cho phép NULL ở mức toàn bảng**, dù logic nghiệp vụ yêu cầu chúng không được null đối với subtype tương ứng. Validation tại Java và ràng buộc CHECK có điều kiện ở DB có thể bổ sung:

~~~sql
ALTER TABLE assets
ADD CONSTRAINT ck_digital_download_url
CHECK (
    asset_kind <> 'DIGITAL'
    OR download_url IS NOT NULL
);

ALTER TABLE assets
ADD CONSTRAINT ck_physical_weight
CHECK (
    asset_kind <> 'PHYSICAL'
    OR weight_grams IS NOT NULL
);
~~~

Hai CHECK trên là ví dụ thiết kế database khi `asset_kind` chỉ nhận các discriminator hợp lệ; tùy dialect, cần dùng migration tương ứng. `@Column(nullable = false)` trên field subtype không thể tự giải quyết mọi ràng buộc điều kiện của một bảng chứa nhiều loại entity.

### 4.4. Khi nào phù hợp?

`SINGLE_TABLE` có lợi khi:

- Hierarchy không có quá nhiều thuộc tính đặc thù ở từng subtype.
- Đọc đa hình nhiều và muốn tránh join qua bảng subclass.
- Muốn một PK/unique constraint dễ quản lý trên toàn hệ phân cấp.

Nhược điểm:

- Bảng có thể có nhiều cột `NULL` đối với subtype khác.
- Khó dùng ràng buộc `NOT NULL` thuần cho các trường chỉ bắt buộc ở một subtype.
- Thêm một subtype với nhiều cột riêng làm bảng root phình to.
- Một số ràng buộc unique có điều kiện phải thể hiện bằng constraint/index DB riêng, không chỉ annotation JPA.

**Kết luận về ID:** `SINGLE_TABLE` dùng một primary key vật lý chung, nên định danh giữa các subtype được DB cưỡng chế trực tiếp tại bảng root.

## 5. JOINED: các bảng subtype chia sẻ cùng khóa root

`JOINED` được dùng trong ví dụ entity hoàn chỉnh ở mục 2. Có một bảng root và bảng riêng cho các phần dữ liệu subtype.

### 5.1. Schema minh họa

~~~sql
CREATE SEQUENCE asset_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(50) NOT NULL
);

CREATE TABLE digital_assets (
    asset_id BIGINT PRIMARY KEY,
    download_url VARCHAR(500) NOT NULL,
    CONSTRAINT fk_digital_asset_base
        FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE TABLE physical_assets (
    asset_id BIGINT PRIMARY KEY,
    weight_grams INTEGER NOT NULL,
    CONSTRAINT fk_physical_asset_base
        FOREIGN KEY (asset_id) REFERENCES assets(id)
);
~~~

Một `DigitalAsset` có ID 41 được lưu thành **hai hàng**:

~~~sql
INSERT INTO assets (id, asset_code)
VALUES (41, 'DL-041');

INSERT INTO digital_assets (asset_id, download_url)
VALUES (41, '/files/book.pdf');
~~~

`DigitalAsset#41` vẫn là **một entity**. Bảng `digital_assets` chứa các thuộc tính bổ sung và dùng `asset_id` đồng thời làm PK/FK tới bảng root.

Sơ đồ:

~~~text
                assets
                id  = 41
                     |
             +-------+--------+
             |                |
     digital_assets       physical_assets
     asset_id = 41        asset_id = ...
     download_url         weight_grams
~~~

Trong một hierarchy hợp lệ, mỗi row ở root đại diện cho đúng loại entity thực tế; cách provider nhận biết subtype có thể thông qua sự hiện diện của row ở bảng subclass hoặc discriminator nếu có cấu hình tương ứng. Không nên tự chèn dữ liệu mâu thuẫn vào nhiều bảng subclass cho cùng root ID.

### 5.2. @PrimaryKeyJoinColumn thay đổi điều gì?

Ở subclass:

~~~java
@Entity
@Table(name = "digital_assets")
@PrimaryKeyJoinColumn(
    name = "asset_id",
    referencedColumnName = "id"
)
public class DigitalAsset extends Asset {
    // ...
}
~~~

`name = "asset_id"` là tên cột PK của bảng `digital_assets`; `referencedColumnName = "id"` là cột PK ở bảng parent. Đây là liên kết **giữa bảng của lớp con và bảng của lớp cha trong cùng entity**.

Đừng nhầm `@PrimaryKeyJoinColumn` của `JOINED` với `@OneToOne @MapsId`. Cả hai có thể tạo PK/FK liên kết các bảng, nhưng:

- `JOINED` dùng để lưu **một object có kiểu subclass** qua nhiều bảng theo inheritance.
- `@OneToOne @MapsId` dùng cho **hai entity khác nhau** với định danh phụ thuộc.

### 5.3. Thứ tự INSERT và DELETE

Để tạo `DigitalAsset` mới, provider cần bảo đảm row root có ID trước khi row subclass tham chiếu tới nó.

~~~sql
-- Minh họa thứ tự ràng buộc
INSERT INTO assets (id, asset_code) VALUES (41, 'DL-041');
INSERT INTO digital_assets (asset_id, download_url)
VALUES (41, '/files/book.pdf');
~~~

Khi xóa, DB không có `ON DELETE CASCADE` thường cần xử lý row subclass trước rồi mới root:

~~~sql
DELETE FROM digital_assets WHERE asset_id = 41;
DELETE FROM assets WHERE id = 41;
~~~

Provider quản lý những thao tác này thông qua lifecycle của **một entity subtype**. Thời điểm thực thi SQL có thể thay đổi theo flush và provider; code ứng dụng không cần tạo hai entity riêng để biểu diễn hai hàng.

### 5.4. Ưu và nhược điểm của JOINED

Ưu điểm:

- Các cột chỉ thuộc subtype nằm ở bảng subtype, nên dễ đặt `NOT NULL` phù hợp.
- Hạn chế các cột rỗng không liên quan ở bảng root.
- ID thống nhất tại bảng root.
- Các quan hệ tham chiếu đến root có thể dùng FK tới `assets.id` rõ ràng.

Nhược điểm:

- Đọc subtype thường cần join root và bảng subtype.
- Truy vấn đa hình qua root có thể cần nhiều join hoặc logic bổ sung.
- Lưu/xóa một entity subtype có thể đụng đến nhiều bảng.
- Schema và migration phức tạp hơn `SINGLE_TABLE`.

**Kết luận về ID:** các bảng subtype có cột PK riêng về mặt vật lý, nhưng **giá trị phải giống PK của hàng root**; không sinh số độc lập ở mỗi subtype.

## 6. TABLE_PER_CLASS: mỗi loại cụ thể có bảng riêng

### 6.1. Ý tưởng

`TABLE_PER_CLASS` đưa các thuộc tính kế thừa và thuộc tính riêng của từng concrete entity vào **bảng dành cho concrete class**. Với root `Asset` là abstract, bảng riêng cho root thường không cần thiết để lưu object root, bởi không thể tạo instance trực tiếp của abstract class.

Ví dụ schema:

~~~sql
CREATE TABLE digital_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(50) NOT NULL,
    download_url VARCHAR(500) NOT NULL
);

CREATE TABLE physical_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(50) NOT NULL,
    weight_grams INTEGER NOT NULL
);
~~~

Nếu dùng chiến lược này, thay annotation root của ví dụ thành:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Asset {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "asset_id_generator"
    )
    private Long id;

    // Các thuộc tính chung...
}
~~~

và thiết kế tên bảng phù hợp trên các concrete subclasses.

Đây là **biến thể mapping thay thế**. Không giữ nguyên assumptions về bảng root `assets` có PK khi chuyển từ `JOINED` sang `TABLE_PER_CLASS`.

### 6.2. Giới hạn quan trọng: uniqueness trên toàn hierarchy

Hai bảng `digital_assets` và `physical_assets` có primary key riêng:

~~~text
digital_assets.id          physical_assets.id
       41                         41
      (PK)                       (PK)
~~~

Mỗi bảng có thể chấp nhận ID 41 **nếu chỉ nhìn ràng buộc PK của chính bảng đó**. Nhưng chúng cùng là concrete subtype thuộc một entity hierarchy, nên **không nên để hai loại khác nhau trong cùng hệ phân cấp dùng ID trùng nhau**. Khi JPA truy vấn đa hình và quản lý identity trong hệ phân cấp, khóa cần nhất quán xuyên các bảng.

Với `TABLE_PER_CLASS`, JPA provider không có một bảng root với PK chung để database tự cưỡng chế uniqueness toàn hierarchy. Vì vậy cần một **nguồn cấp ID chung**:

~~~text
            Shared ID generator
                     |
                asset_id_seq
                    / \
                   /   \
                  v     v
       DigitalAsset#41  PhysicalAsset#42
             |                 |
       digital_assets      physical_assets
~~~

Một sequence chung hoặc cơ chế UUID thích hợp có thể giải quyết yêu cầu cấp khóa ở tầng ứng dụng/provider. Nếu dùng hai database sequence riêng bắt đầu cùng giá trị, khả năng trùng khóa giữa subtype là hiện hữu.

Một số ORM, ví dụ các bản Hibernate tương ứng, có hạn chế khi kết hợp `TABLE_PER_CLASS` với `GenerationType.IDENTITY` vì mỗi bảng tự cấp ID có thể gây đụng ID toàn hierarchy. **Không giả định `IDENTITY` trên từng bảng luôn dùng được cho polymorphic inheritance.** Chọn generator được provider hỗ trợ và bảo đảm tính duy nhất xuyên hierarchy.

### 6.3. Truy vấn đa hình có thể sử dụng UNION

JPQL:

~~~jpql
SELECT a
FROM Asset a
ORDER BY a.assetCode
~~~

Với `TABLE_PER_CLASS`, provider có thể cần truy vấn nhiều bảng, ví dụ logic SQL tương đương:

~~~sql
SELECT id, asset_code, 'DIGITAL' AS asset_kind
FROM digital_assets
UNION ALL
SELECT id, asset_code, 'PHYSICAL' AS asset_kind
FROM physical_assets;
~~~

Đây là **minh họa cơ chế UNION**, không phải SQL đầy đủ của mọi provider; truy vấn thực tế còn phải chọn cột riêng, bổ sung giá trị NULL cho cột không thuộc subtype và xử lý sắp xếp/kiểu dữ liệu theo dialect.

Hệ quả:

- Truy vấn theo root có thể tốn chi phí kết hợp nhiều bảng.
- Thêm subtype mới có thể làm truy vấn đa hình rộng hơn.
- Khóa ngoại tới một “Asset bất kỳ” khó thể hiện bằng **một FK thông thường** nếu không có bảng root chung.
- DB thường không thể dùng một ràng buộc UNIQUE/FOREIGN KEY duy nhất trải trên tất cả các bảng subtype.

### 6.4. Khi nào nên chọn TABLE_PER_CLASS?

Cân nhắc khi:

- Các subtype tương đối độc lập và có tập thuộc tính riêng lớn.
- Truy vấn thường đi trực tiếp vào concrete subclass hơn là root.
- Có chiến lược cấp ID toàn hierarchy phù hợp.
- Chấp nhận chi phí query đa hình và hạn chế FK chung.

Không nên chọn chỉ vì “mỗi class Java muốn một bảng riêng”. Việc không có root table để cưỡng chế định danh chung có thể gây phức tạp cho mối quan hệ và dữ liệu tích hợp.

## 7. So sánh ba chiến lược theo định danh và ánh xạ

| Tiêu chí | `SINGLE_TABLE` | `JOINED` | `TABLE_PER_CLASS` |
| --- | --- | --- | --- |
| Bảng lưu hierarchy | Một bảng | Bảng root + bảng subtype | Bảng cho từng concrete class |
| Cột ID | Một PK trong bảng chung | PK root và PK/FK ở subtype | PK riêng tại bảng concrete |
| Identity logic của entity subtype | Một ID từ root hierarchy | Một ID từ root hierarchy | Cần ID thống nhất/không va chạm trong hierarchy |
| Generator nên dùng | Phù hợp root, thống nhất | Phù hợp root, thống nhất | Nguồn ID chung rất quan trọng |
| Discriminator | Thường cần để phân biệt subtype | Có thể dùng, phụ thuộc mapping/provider | Không dựa vào một cột discriminator chung |
| Cột chỉ thuộc subtype | Trong bảng chung; thường nullable | Trong bảng subtype, đặt NOT NULL trực tiếp | Trong bảng concrete, đặt NOT NULL trực tiếp |
| JOIN khi đọc subtype | Thường không cần join do inheritance | Thường cần join root + subtype | Thường không cần join root |
| Query root đa hình | Một bảng | Có thể nhiều join | Có thể UNION qua nhiều bảng |
| FK tới root entity | Đơn giản | Đơn giản tới bảng root | Khó cưỡng chế bằng một FK DB duy nhất |
| Điểm cần chú ý | Cột subtype và constraints điều kiện | PK/FK giữa các bảng và chi phí join | Global ID, UNION và quan hệ đa hình |

Không có chiến lược nào “tốt nhất cho mọi hệ thống”. Hãy chọn theo **định danh**, **quan hệ FK**, **cách truy vấn**, **mức độ khác biệt giữa các subtype** và **ràng buộc schema**.

## 8. @MappedSuperclass khác root @Entity như thế nào?

### 8.1. Tái sử dụng mapping nhưng không tạo hierarchy entity chung

Một kiểu base khác:

~~~java
package com.example.assets.domain;

import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class BaseRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    protected Long id;

    @Column(name = "created_by", length = 100)
    protected String createdBy;

    public Long getId() {
        return id;
    }
}
~~~

Các entity độc lập:

~~~java
@Entity
@Table(name = "suppliers")
public class Supplier extends BaseRecord {
    // ...
}

@Entity
@Table(name = "warehouses")
public class Warehouse extends BaseRecord {
    // ...
}
~~~

Cả `Supplier` và `Warehouse` được thừa hưởng khai báo `@Id` và `createdBy`. Tuy nhiên:

- `BaseRecord` **không phải entity**.
- Không dùng `em.find(BaseRecord.class, ...)`.
- Không dùng JPQL `FROM BaseRecord` để lấy cả Supplier lẫn Warehouse.
- Không có nghĩa Supplier và Warehouse thuộc **một JPA entity inheritance hierarchy duy nhất**.
- ID của `Supplier#1` và `Warehouse#1` có thể giống nhau nếu các bảng/generator được cấu hình độc lập, vì chúng là **hai entity root khác nhau**.

Đây là sự khác biệt rất quan trọng giữa **tái sử dụng trường ID** và **chia sẻ identity space của một entity hierarchy**.

### 8.2. @MappedSuperclass có thể nằm phía trên entity root

Một hierarchy có thể được tổ chức như sau:

~~~text
BaseRecord (@MappedSuperclass)
      |
     Asset (@Entity, @Inheritance)
      |
   +-- DigitalAsset (@Entity)
   +-- PhysicalAsset (@Entity)
~~~

Trong trường hợp này, `Asset` thừa hưởng metadata `@Id` từ `BaseRecord`. `Asset` vẫn là **root entity** của hệ phân cấp giữa Asset và các subclass. Các subtype không tự sinh thêm định danh chỉ vì metadata ID được khai báo cao hơn ở mapped superclass.

Một nguyên tắc hữu ích: **vị trí khai báo Java của `@Id` và ranh giới entity hierarchy không phải lúc nào trùng nhau**. `@Id` có thể được thừa hưởng từ `@MappedSuperclass`; nhưng JPA quản lý polymorphic identity từ **root entity** thực sự.

### 8.3. Mapped superclass không thể làm target quan hệ entity

Ví dụ không phù hợp:

~~~java
// Không thể xem BaseRecord như target entity polymorphic:
@ManyToOne
private BaseRecord owner;
~~~

`BaseRecord` không là entity, nên không có bảng/identity entity để JPA mapping quan hệ đa hình tới nó. Nếu nghiệp vụ cần một association đến nhiều subtype, phải có **entity root phù hợp**, một bảng tham chiếu có thiết kế rõ ràng, hoặc một mô hình quan hệ khác.

## 9. Giới hạn của @AttributeOverride và @AssociationOverride khi kế thừa

Kế thừa giúp chia sẻ thuộc tính mapping, nhưng có những trường hợp cần đổi tên cột khi tái sử dụng mapping từ `@MappedSuperclass`.

### 9.1. Override cột của thuộc tính kế thừa từ mapped superclass

Giả sử:

~~~java
@MappedSuperclass
public abstract class AuditFields {

    @Column(name = "created_by")
    protected String createdBy;

    @Column(name = "created_at")
    protected java.time.Instant createdAt;
}
~~~

Một entity kế thừa:

~~~java
@Entity
@Table(name = "supplier_accounts")
@AttributeOverride(
    name = "createdBy",
    column = @Column(name = "creator_login", length = 120)
)
public class SupplierAccount extends AuditFields {

    @Id
    private Long id;
}
~~~

`@AttributeOverride(name = "createdBy")` dùng **tên thuộc tính Java** được kế thừa, còn `@Column(name = "creator_login")` khai báo tên cột vật lý tại bảng entity này.

Đây là một ứng dụng thông dụng của override khi mapping được chia sẻ từ **mapped superclass** hoặc embeddable.

### 9.2. Với association kế thừa, dùng @AssociationOverride

Nếu mapped superclass có:

~~~java
@MappedSuperclass
public abstract class OwnedRecord {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    protected AppUser owner;
}
~~~

Một entity cụ thể muốn đổi cột FK:

~~~java
@Entity
@Table(name = "documents")
@AssociationOverride(
    name = "owner",
    joinColumns = @JoinColumn(name = "created_by_user_id")
)
public class Document extends OwnedRecord {

    @Id
    private Long id;
}
~~~

`@AssociationOverride` dùng cho association mapping; `@AttributeOverride` dùng cho basic/embedded attributes. Không dùng `@AttributeOverride` để đổi tên join column của một `@ManyToOne`.

### 9.3. Không coi override là cách đổi identity của subclass

Nếu root `Asset` đã có `@Id Long id`, một subclass không nên dùng `@AttributeOverride` để “tạo một khóa chính mới” hoặc thay nguồn sinh ID chỉ cho nó.

Hãy phân biệt:

- **Override metadata của thuộc tính kế thừa** trong phạm vi JPA cho phép, ví dụ đổi tên cột của mapped superclass.
- **Thay chiến lược inheritance** bằng `@Inheritance` trên root entity.
- **Đặt cột PK/FK của bảng subclass** trong `JOINED` bằng `@PrimaryKeyJoinColumn`.
- **Định nghĩa entity identity** bằng `@Id`/`@EmbeddedId` tại hierarchy phù hợp.

Bốn thao tác trên giải quyết những vấn đề khác nhau.

## 10. Tên bảng và cột được quyết định theo hierarchy

Không nên mặc định mỗi `@Entity` đều có thể chọn bảng độc lập trong mọi chiến lược.

### Với SINGLE_TABLE

~~~java
@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
abstract class Asset { ... }

@Entity
class DigitalAsset extends Asset { ... }
~~~

`DigitalAsset` dùng **bảng root**. Một `@Table(name = "digital_assets")` đặt trên subclass không làm provider tạo thêm bảng subtype đúng như `JOINED`; ý nghĩa thực tế phải tuân theo strategy được chọn.

### Với JOINED

~~~java
@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.JOINED)
abstract class Asset { ... }

@Entity
@Table(name = "digital_assets")
class DigitalAsset extends Asset { ... }
~~~

Tên `digital_assets` áp dụng cho bảng chứa cột riêng của subtype, với PK/FK nối về `assets`.

### Với TABLE_PER_CLASS

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
abstract class Asset { ... }

@Entity
@Table(name = "digital_assets")
class DigitalAsset extends Asset { ... }
~~~

Bảng `digital_assets` chứa cả trường `asset_code` kế thừa và `download_url` riêng.

**Không thể kết hợp các ý tưởng tùy ý**, ví dụ mong cùng một root entity vừa dùng SINGLE_TABLE cho subtype A, vừa JOINED cho subtype B, nếu không có cơ chế provider đặc thù ngoài phạm vi mapping portable. JPA chuẩn chọn **một inheritance strategy cho một entity hierarchy**.

## 11. Truy vấn đa hình và kiểu thực của entity

Khi `Asset` là `@Entity` root, JPQL có thể truy vấn:

~~~java
List<Asset> assets = em.createQuery(
    """
    SELECT a
    FROM Asset a
    ORDER BY a.id
    """,
    Asset.class
).getResultList();
~~~

Danh sách trả về có thể gồm `DigitalAsset` và `PhysicalAsset` theo dữ liệu, dù biến trong Java có kiểu `Asset`. Đó là **polymorphic query**.

### 11.1. Truy vấn trực tiếp một subtype

~~~java
List<DigitalAsset> digitalAssets = em.createQuery(
    """
    SELECT d
    FROM DigitalAsset d
    WHERE d.downloadUrl IS NOT NULL
    """,
    DigitalAsset.class
).getResultList();
~~~

Truy vấn từ subtype này không cần lấy các entity `PhysicalAsset`.

### 11.2. TYPE và TREAT

JPQL hỗ trợ lọc theo kiểu entity:

~~~java
List<Asset> onlyDigital = em.createQuery(
    """
    SELECT a
    FROM Asset a
    WHERE TYPE(a) = DigitalAsset
    """,
    Asset.class
).getResultList();
~~~

Khi cần truy cập field chỉ có ở subtype trong một truy vấn qua root, JPA hỗ trợ `TREAT` theo phiên bản đặc tả thích hợp:

~~~jpql
SELECT a
FROM Asset a
WHERE TREAT(a AS DigitalAsset).downloadUrl = :url
~~~

Cú pháp `TYPE` và `TREAT` có ý nghĩa ở **entity inheritance hierarchy**; không thể dùng `TYPE(a)` với một `@MappedSuperclass` như thể nó là entity query root.

### 11.3. ID giống nhau không đủ để suy ra cùng entity

Trong hệ phân cấp, JPA nhận biết cả kiểu entity thực tế. Hai reference Java có thể được truy xuất bằng nhiều query khác nhau nhưng cùng biểu diễn một entity đã managed, ví dụ `Asset#41` thực chất là `DigitalAsset#41`.

Ngược lại, `Supplier#41` và `Warehouse#41` kế thừa cùng `@MappedSuperclass BaseRecord` vẫn là **hai entity độc lập**. Chỉ vì đều có field tên `id` và cùng giá trị `41` không khiến chúng là một đối tượng persistent.

### 11.4. equals/hashCode không tự động được JPA cài đặt bằng ID

Entity class có thể dùng Java reference equality mặc định hoặc tự triển khai `equals/hashCode`. Với inheritance, việc tự viết `equals` càng cần suy nghĩ về:

- So sánh giữa root và subclass.
- ID chưa được cấp cho entity mới.
- Proxy của provider và class runtime.
- Tính ổn định của `hashCode` nếu ID được gán sau khi đưa object vào `HashSet`.

**Đừng đồng nhất JPA persistence identity với Java `equals()` ở mọi entity.** Nếu dự án định nghĩa equality dựa trên ID, phải có chính sách nhất quán cho toàn hierarchy và kiểm tra các tình huống new/managed/detached. Bài học này tập trung vào **định danh ORM**, không yêu cầu một công thức `equals/hashCode` duy nhất cho mọi ứng dụng.

## 12. Kế thừa khóa ghép có được không?

Một root entity có thể dùng khóa ghép theo mô hình `@EmbeddedId` hoặc `@IdClass` khi nghiệp vụ yêu cầu. Điểm quan trọng là các subclass vẫn **kế thừa cùng định danh đó**, không tự thiết lập thêm một bộ khóa riêng.

Ví dụ rút gọn:

~~~java
@Embeddable
public class AssetId implements java.io.Serializable {

    private String tenantCode;
    private Long localNumber;

    protected AssetId() {
    }

    // Constructor, getters, equals và hashCode...
}
~~~

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Asset {

    @EmbeddedId
    private AssetId id;

    // Thuộc tính chung...
}
~~~

Một subtype:

~~~java
@Entity
public class DigitalAsset extends Asset {

    private String downloadUrl;

    // Không khai báo thêm @Id.
}
~~~

Với `JOINED`, việc tạo bảng subclass đòi hỏi **khóa chính/khóa ngoại ghép** tham chiếu tới bộ cột khóa của root. Annotation và schema cần ánh xạ đầy đủ mọi thành phần khóa, không được lấy mỗi một phần rồi coi đó là định danh đủ của subclass.

Khi khóa ghép chứa quan hệ derived identity, có thể cần `@MapsId` và các annotation liên quan trong mô hình thích hợp; tuy nhiên **derived identity giữa hai entity liên kết** khác với **PK join giữa bảng root/subclass của entity inheritance**.

## 13. Truy vấn và quan hệ khi target là root entity

Ví dụ một `Campaign` liên kết đến một tài sản bất kỳ:

~~~java
@Entity
public class Campaign {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "featured_asset_id")
    private Asset featuredAsset;
}
~~~

Đây là ví dụ association tới **entity root `Asset`**. Do `Asset` là entity, JPA có thể trả instance thực tế là `DigitalAsset` hoặc `PhysicalAsset`.

Ở database:

- Với `SINGLE_TABLE`, FK có thể trỏ thẳng `assets.id`.
- Với `JOINED`, FK cũng có thể trỏ `assets.id` vì tất cả subtype có hàng root.
- Với `TABLE_PER_CLASS` và root abstract không có bảng root, một FK SQL duy nhất trỏ tới “mọi bảng concrete asset” không được diễn đạt bằng một FK thông thường. Provider có thể hỗ trợ truy vấn đa hình nhưng database constraint trở nên khó thiết kế hơn.

Nếu một phần lớn mô hình có quan hệ tới “bất kỳ subtype nào của Asset”, đây là lý do quan trọng để cân nhắc `SINGLE_TABLE` hoặc `JOINED` thay cho `TABLE_PER_CLASS`.

### 13.1. Association đến subclass cụ thể

Nếu trường có kiểu `DigitalAsset`:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "featured_digital_asset_id")
private DigitalAsset digitalAsset;
~~~

association chỉ chấp nhận concrete subclass phù hợp. Với `JOINED`, mapping FK ở DB có thể trỏ bảng subtype hoặc bảng phù hợp theo mapping/provider; khi cần ràng buộc chỉ cho phép digital asset, cần kiểm tra thiết kế FK/PK thực tế.

## 14. Không phải mọi khác biệt nghiệp vụ đều cần subclass entity

Một mô hình phân cấp có thể hấp dẫn ở tầng Java nhưng làm schema phức tạp không cần thiết.

Ví dụ hai loại Asset chỉ khác một thuộc tính `formatCode` và không có hành vi riêng. Có thể chỉ cần:

~~~java
@Entity
public class Asset {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private AssetKind kind;

    private String formatCode;
}
~~~

Hoặc dùng **composition**:

~~~java
@Entity
public class Asset {
    @Id
    private Long id;

    @Embedded
    private AssetDetails details;
}
~~~

Hai ví dụ là **phương án thiết kế thay thế**, không phải code kết hợp trực tiếp với hierarchy trước đó.

| Nhu cầu | Thiết kế nên cân nhắc |
| --- | --- |
| Có hành vi và thuộc tính khác nhau theo subtype, cần query đa hình | Entity inheritance |
| Chỉ cần vài field phân loại, không có subclass behavior đáng kể | Một entity với enum |
| Nhóm field là value object không có ID riêng | `@Embeddable` + `@Embedded` |
| Hai đối tượng có vòng đời và identity riêng, liên kết với nhau | Association `@OneToOne`, `@ManyToOne`... |
| Muốn tái sử dụng ID và audit field giữa nhiều entity độc lập | `@MappedSuperclass` |

Đặc biệt, không nhầm `@MappedSuperclass` với entity inheritance. Việc hai entity cùng kế thừa một Java base class không nhất thiết có nghĩa chúng được lưu như một hierarchy ORM.

## 15. Giới hạn về ràng buộc UNIQUE trong các chiến lược

Giả sử `assetCode` phải duy nhất **trên toàn bộ hệ phân cấp**, bất kể subtype.

### SINGLE_TABLE

~~~sql
ALTER TABLE assets
ADD CONSTRAINT uk_assets_code UNIQUE (asset_code);
~~~

Bởi vì mọi subtype nằm trong một bảng, unique constraint đơn giản và rõ ràng.

### JOINED

~~~sql
ALTER TABLE assets
ADD CONSTRAINT uk_assets_code UNIQUE (asset_code);
~~~

`assetCode` được lưu ở bảng root, nên unique constraint root kiểm tra toàn hierarchy.

### TABLE_PER_CLASS

~~~text
digital_assets(asset_code UNIQUE)
physical_assets(asset_code UNIQUE)
~~~

Hai unique constraint ở hai bảng riêng **không ngăn** cùng `assetCode` xuất hiện ở cả hai bảng. Nếu thật sự cần uniqueness xuyên hierarchy, phải có cơ chế bổ sung như bảng đăng ký mã chung, dịch vụ cấp phát được giao dịch hóa hoặc lựa chọn lại inheritance strategy.

Tương tự với ID: một PK tại mỗi concrete table không tự kiểm tra uniqueness xuyên tất cả bảng. Đây là giới hạn của **ràng buộc ở mức schema**, không thể được giải quyết chỉ bằng cách đặt `@Column(unique = true)` trên field kế thừa.

## 16. Giới hạn về thay đổi subtype của entity đã tồn tại

Giả sử database hiện có `DigitalAsset#41`, sau đó nghiệp vụ muốn “đổi nó thành `PhysicalAsset#41`”.

Không thể chỉ gọi:

~~~java
Asset asset = em.find(Asset.class, 41L);

// Không có thao tác JPA chuẩn:
// em.changeEntityType(asset, PhysicalAsset.class);
~~~

JPA không cung cấp một API tổng quát để biến **managed instance thuộc một entity subtype** thành instance của subtype khác nhưng giữ nguyên identity và trạng thái persistence. Class runtime của object không thể bị thay tại chỗ.

Ở tầng SQL, thao tác cũng phức tạp:

- `SINGLE_TABLE`: cần đổi discriminator, dọn/điền các cột subtype và bảo đảm các ràng buộc điều kiện.
- `JOINED`: cần thay dòng ở bảng subclass, giữ root ID và liên kết liên quan.
- `TABLE_PER_CLASS`: cần chuyển hàng giữa các bảng concrete và kiểm tra uniqueness/quan hệ.

Các bước này có thể làm các entity/proxy đang managed trở nên không nhất quán. Do đó, nếu “đổi loại tài sản” là một nghiệp vụ thường xuyên, hãy cân nhắc **một entity với type field và composition**, hoặc một quy trình migration dữ liệu có kiểm soát. **Subtyping entity thường phù hợp khi loại entity tương đối ổn định trong vòng đời của nó.**

## 17. Kế thừa nhiều tầng và giới hạn chiến lược

Một hệ phân cấp có thể có nhiều tầng:

~~~text
Asset (@Entity, root)
  |
  +-- DigitalAsset (@Entity, abstract)
         |
         +-- DownloadableBook (@Entity)
         +-- VideoCourse (@Entity)
  |
  +-- PhysicalAsset (@Entity)
~~~

Vẫn phải suy nghĩ tới:

1. **Một ID logic** được kế thừa qua các tầng.
2. Chiến lược `@Inheritance` tại root được áp dụng cho mapping hệ phân cấp.
3. Các bảng cụ thể và PK/FK theo chiến lược đã chọn.
4. Truy vấn `FROM Asset`, `FROM DigitalAsset` và `FROM DownloadableBook` tương ứng phạm vi các kiểu được phép.
5. Tên entity/discriminator tránh va chạm và phản ánh schema nhất quán.

Không cố áp dụng `JOINED` cho riêng nhánh `DigitalAsset` rồi `SINGLE_TABLE` cho nhánh `PhysicalAsset` như một cấu hình JPA portable của cùng root, vì đó là các chiến lược mapping hierarchy khác nhau. Nếu cần kết hợp phức tạp ngoài khả năng JPA chuẩn, phải đánh giá tính năng provider cụ thể và khả năng duy trì lâu dài.

## 18. Khi thiết kế migration, phải đánh giá identity trước

Đổi từ `SINGLE_TABLE` sang `JOINED` hoặc từ `JOINED` sang `TABLE_PER_CLASS` là **thay đổi mô hình lưu dữ liệu**, không phải chỉ sửa annotation.

### Ví dụ: SINGLE_TABLE sang JOINED

Trạng thái ban đầu:

~~~text
assets(
    id PK,
    asset_kind,
    asset_code,
    download_url,
    weight_grams
)
~~~

Trạng thái đích:

~~~text
assets(id PK, asset_code)
digital_assets(asset_id PK/FK, download_url)
physical_assets(asset_id PK/FK, weight_grams)
~~~

Một kế hoạch tổng quát:

1. Tạo bảng subtype với PK/FK tham chiếu bảng root.
2. Sao chép dữ liệu subtype dựa trên discriminator, **giữ nguyên ID**.
3. Kiểm tra mỗi row root có đúng subtype cần thiết.
4. Cập nhật ứng dụng/mapping theo lộ trình triển khai.
5. Chuyển ràng buộc `NOT NULL`, `UNIQUE` và các index tương ứng.
6. Chỉ loại bỏ cột cũ khi các ứng dụng và truy vấn đã chuyển hoàn toàn.

Không nên tạo ID mới khi chuyển dữ liệu subclass nếu các hệ thống bên ngoài đang tham chiếu ID cũ. Giữ identity là yêu cầu quan trọng trong migration kế thừa.

### Đổi sang TABLE_PER_CLASS

Cần xem thêm:

- Không còn một bảng root thống nhất để mọi association trỏ tới.
- ID và unique value có thể va chạm giữa các bảng concrete.
- Truy vấn root thay đổi sang cơ chế đa bảng/union.
- FK tới root hoặc audit/event dùng ID phải được thiết kế lại.

Nếu dự án có nhiều relation tới root entity, chi phí chuyển sang `TABLE_PER_CLASS` có thể lớn hơn rất nhiều so với việc chỉ tách một vài cột.

## 19. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Subclass khai báo `@Id` mới | Nhầm một subtype với entity root độc lập | Để khóa thuộc root/mapped superclass, không thêm PK độc lập |
| `DigitalAsset.id` và `PhysicalAsset.id` trùng khi TABLE_PER_CLASS | Mỗi bảng tự cấp ID riêng | Dùng nguồn ID chung/thiết kế ID phù hợp toàn hierarchy |
| FK giữa bảng JOINED lỗi khi insert | Chưa có row root tương ứng hoặc PK join sai | Kiểm tra `@PrimaryKeyJoinColumn` và schema PK/FK |
| Một subclass field NOT NULL gây lỗi ở subtype khác | SINGLE_TABLE có các cột subtype cùng một bảng | Cho phép null ở schema chung và dùng constraint theo discriminator/validation |
| JPQL `FROM BaseRecord` không hoạt động | `BaseRecord` là `@MappedSuperclass` | Query entity root hoặc entity cụ thể |
| `@Table` trên subclass không tạo bảng mong đợi | Root đang dùng SINGLE_TABLE | Xác định `@Inheritance` và schema thực tế |
| Truy vấn `FROM Asset` chậm | JOINED tạo join hoặc TABLE_PER_CLASS tạo union | Đánh giá plan và chiến lược theo workload |
| Không thể khai báo một FK tới mọi concrete subtype | TABLE_PER_CLASS thiếu root table thống nhất | Cân nhắc SINGLE_TABLE/JOINED hoặc mô hình tham chiếu khác |
| `@AttributeOverride` không đổi khóa của subclass | Override field không tạo identity riêng | Thiết kế @Id tại root, PK join theo inheritance |
| `@AssociationOverride` dùng sai cho basic field | Nhầm association với thuộc tính thường | Dùng `@AttributeOverride` cho basic/embeddable mapping |
| Dùng Java `final`/record làm entity subtype | Không phù hợp với ràng buộc entity class portable | Dùng class entity đáp ứng yêu cầu JPA |
| Muốn thay discriminator sau khi persist | Thực chất là thay entity type | Thiết kế migration hoặc dùng model composition/type field |
| Đổi strategy làm mất liên kết ID | Migration thay đổi bảng/khóa nhưng không chuyển FK đầy đủ | Lên kế hoạch giữ identity và cập nhật tham chiếu |

## 20. Tình huống thực hành

### Bài 1. Root đã có @Id, subclass có cần @Id khác?

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
abstract class Asset {
    @Id
    Long id;
}

@Entity
class DigitalAsset extends Asset {
    String downloadUrl;
}
~~~

**Đáp án:** Không. `DigitalAsset` kế thừa ID từ `Asset`. Trong `JOINED`, bảng của `DigitalAsset` có thể có PK/FK trỏ bảng root, nhưng Java entity không khai báo primary key khác.

### Bài 2. Vì sao hai bảng JOINED cùng lưu ID 90?

~~~text
assets.id = 90
digital_assets.asset_id = 90
~~~

**Đáp án:** Hai hàng là các phần lưu trữ của **cùng một entity `DigitalAsset#90`**. `asset_id` tại bảng child là PK/FK về bảng root, không phải ID của một entity độc lập.

### Bài 3. SINGLE_TABLE có thể đặt download_url NOT NULL cho mọi hàng?

**Đáp án:** Không nếu subtype `PhysicalAsset` không có thuộc tính downloadUrl. Cần cho phép NULL ở cấp bảng chung và kiểm tra có điều kiện theo discriminator, hoặc thiết kế mapping khác.

### Bài 4. Supplier và Warehouse cùng kế thừa @MappedSuperclass, ID cùng bằng 1 có lỗi không?

**Đáp án:** Không nhất thiết. Nếu chúng là hai entity root độc lập, mỗi bảng có ID 1 là bình thường. `@MappedSuperclass` chỉ chia sẻ metadata, không tạo một entity hierarchy đa hình có ID chung.

### Bài 5. TABLE_PER_CLASS dùng hai sequence riêng có vấn đề gì?

**Đáp án:** Hai sequence có thể cấp cùng một ID cho hai subclass. Nếu các entity cùng hierarchy phải được quản lý và truy vấn đa hình, đây là thiết kế định danh không nhất quán. Nên dùng nguồn cấp ID chung và bảo đảm tính duy nhất toàn hierarchy.

### Bài 6. @PrimaryKeyJoinColumn có giống @MapsId không?

**Đáp án:** Cùng liên quan đến PK/FK nhưng khác ngữ nghĩa. `@PrimaryKeyJoinColumn` trong `JOINED` nối bảng root/subclass của **một entity**; `@OneToOne @MapsId` biểu diễn **hai entity riêng** có khóa phụ thuộc.

### Bài 7. Vì sao FK tới Asset khó với TABLE_PER_CLASS?

**Đáp án:** Vì có thể không tồn tại bảng root chứa tất cả asset ID, còn ID thực nằm ở nhiều concrete table. Một FK thông thường cần một bảng/cột đích cụ thể; nó không trỏ đồng thời đến nhiều bảng subtype một cách portable.

### Bài 8. Một asset đang là DigitalAsset có thể đổi sang PhysicalAsset bằng setter không?

**Đáp án:** Không. Đây là thay đổi kiểu entity và mapping lưu trữ, không phải thay giá trị một field. Cần quy trình dữ liệu thích hợp hoặc chọn mô hình với trường phân loại thay vì subclass nếu việc đổi loại xảy ra thường xuyên.

### Bài 9. Truy vấn từ root có trả các subclass không?

~~~jpql
SELECT a FROM Asset a
~~~

**Đáp án:** Có thể trả mọi concrete entity thuộc hierarchy phù hợp, vì `Asset` là root entity; nếu `Asset` chỉ là `@MappedSuperclass` thì JPQL trên không hợp lệ với vai trò entity root.

## 21. Tổng kết nguyên tắc thiết kế

Giới hạn định danh và ánh xạ trong hệ phân cấp có thể cô đọng thành các nguyên tắc:

1. **Khai báo một identity model cho entity hierarchy**: `@Id`/`@EmbeddedId` ở root entity hoặc được root kế thừa từ mapped superclass, không tự tạo primary key độc lập ở subclass.
2. **Chọn đúng chiến lược lưu bảng**: `SINGLE_TABLE` có một bảng và discriminator; `JOINED` có PK/FK giữa root và subtype; `TABLE_PER_CLASS` dùng nhiều bảng concrete và cần kiểm soát uniqueness toàn hierarchy.
3. **Đừng nhầm Java inheritance với JPA entity inheritance**: `@MappedSuperclass` chia sẻ metadata nhưng không là entity truy vấn đa hình.
4. **Giới hạn constraint phụ thuộc strategy**: SINGLE_TABLE khó đặt NOT NULL chung cho trường chỉ thuộc một subtype; TABLE_PER_CLASS khó cưỡng chế uniqueness/FK toàn hierarchy; JOINED tăng số bảng và join.
5. **Không dùng override để thay ID của subtype**: `@AttributeOverride`/`@AssociationOverride` giải quyết chi tiết mapping kế thừa phù hợp, còn `@PrimaryKeyJoinColumn` nối bảng subclass với root trong JOINED.
6. **Truy vấn đa hình có chi phí và quy tắc riêng**: query root có thể trả subtype; TYPE/TREAT hoạt động với hierarchy entity; SQL thực tế có thể dùng discriminator, join hoặc union.
7. **Chọn inheritance theo vòng đời và quan hệ**: nếu subtype thường xuyên đổi loại hoặc cần identity độc lập, cân nhắc một entity với type field, composition, hoặc các entity liên kết thay vì cố dùng kế thừa.

Ghi nhớ hình ảnh cuối: **một đối tượng `DigitalAsset` có một định danh JPA**, dù dữ liệu của nó nằm trong **một hàng chung** (`SINGLE_TABLE`), **một hàng root cộng một hàng subclass** (`JOINED`), hay **một hàng trong bảng concrete** (`TABLE_PER_CLASS`). Cách phân bố hàng có thể khác, nhưng không được biến mỗi class con thành một hệ thống khóa và ánh xạ tùy ý tách khỏi mô hình hierarchy đã chọn.
