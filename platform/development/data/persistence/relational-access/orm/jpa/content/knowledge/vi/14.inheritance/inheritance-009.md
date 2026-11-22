# Đánh giá ràng buộc cột, số phép nối và chi phí truy vấn trong kế thừa JPA

## 1. Vì sao chiến lược kế thừa ảnh hưởng tới database?

Kế thừa là một cơ chế quen thuộc của Java: lớp con dùng lại trạng thái và hành vi từ lớp cha. Trong Jakarta Persistence (JPA), nếu **lớp cha và các lớp con đều là entity trong một hệ phân cấp**, cần quyết định cách biểu diễn hệ phân cấp đó bằng **bảng quan hệ**. Quyết định này ảnh hưởng trực tiếp tới ba vấn đề:

1. **Ràng buộc cột:** một thuộc tính chỉ bắt buộc đối với một loại entity con có thể khai báo NOT NULL, UNIQUE, FOREIGN KEY và CHECK ở đâu?
2. **Số phép nối:** muốn đọc đầy đủ dữ liệu một entity con hoặc truy vấn đa hình (*polymorphic query*) thì cần bao nhiêu JOIN, có phải dùng UNION hay không?
3. **Chi phí truy vấn:** hệ quản trị phải đọc bao nhiêu bảng, hàng, index và byte; việc INSERT/UPDATE, phân trang và truy vấn qua quan hệ khác chịu ảnh hưởng gì?

Đây không chỉ là chuyện chọn annotation rồi để ORM tạo schema. Hai ứng dụng có cùng class Java nhưng khác chiến lược kế thừa có thể tạo SQL rất khác nhau.

JPA cung cấp ba chiến lược kế thừa entity chính:

- **SINGLE_TABLE:** toàn bộ hệ phân cấp entity nằm trong một bảng.
- **JOINED:** lớp cha và từng lớp con có bảng riêng, liên kết bằng cùng khóa chính.
- **TABLE_PER_CLASS:** mỗi lớp entity concrete có bảng riêng chứa cả thuộc tính được kế thừa.

Ngoài ra, **@MappedSuperclass** giúp dùng lại mapping ở lớp cha nhưng **không tạo một hệ phân cấp entity có thể truy vấn đa hình từ lớp cha**. Đây là một phương án quan trọng khi bài toán không cần đa hình ở tầng persistence.

> Không có chiến lược nào luôn tốt nhất. **SINGLE_TABLE** thường ít JOIN nhất nhưng khó áp đặt NOT NULL riêng cho từng subtype; **JOINED** chuẩn hóa và ràng buộc cột rõ hơn nhưng thường cần JOIN; **TABLE_PER_CLASS** tránh JOIN cha–con khi đọc một subtype nhưng truy vấn đa hình có thể cần UNION và khó đảm bảo uniqueness toàn hệ.

## 2. Một domain để so sánh nhất quán

Giả sử ứng dụng quản lý tài sản, với lớp cha trừu tượng **Asset** và hai loại con:

~~~text
                 Asset
      id, assetCode, displayName
                 / \
                /   \
           Laptop   Vehicle
       serialNumber    vin
       ramGb           seatCount
~~~

Yêu cầu nghiệp vụ:

- Mỗi Asset có **id** và **assetCode** duy nhất trong toàn hệ thống.
- **displayName** bắt buộc với mọi tài sản.
- Laptop bắt buộc có **serialNumber** và có **ramGb** dương.
- Vehicle bắt buộc có **vin** và có **seatCount** dương.
- Cần truy vấn cả **tất cả tài sản**, **chỉ Laptop** và **chi tiết một Vehicle**.
- Có các bảng bên ngoài có thể muốn tham chiếu **Asset bất kể subtype**.

Những yêu cầu này cho thấy trade-off rõ ràng giữa ràng buộc theo loại và truy vấn đa hình.

### 2.1. Mapping SINGLE_TABLE làm cơ sở

Ví dụ dùng Jakarta Persistence và khóa số cấp bằng sequence ở PostgreSQL:

~~~java
package com.example.assets;

import jakarta.persistence.*;

@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "asset_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 20
)
public abstract class Asset {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "asset_id_generator"
    )
    @SequenceGenerator(
        name = "asset_id_generator",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, unique = true, length = 40)
    private String assetCode;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    @Version
    private long version;

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

Hai subtype:

~~~java
package com.example.assets;

import jakarta.persistence.*;

@Entity
@DiscriminatorValue("LAPTOP")
public class Laptop extends Asset {

    @Column(name = "serial_number", length = 80)
    private String serialNumber;

    @Column(name = "ram_gb")
    private Integer ramGb;

    protected Laptop() {}

    public Laptop(
        String assetCode,
        String displayName,
        String serialNumber,
        Integer ramGb
    ) {
        super(assetCode, displayName);
        this.serialNumber = serialNumber;
        this.ramGb = ramGb;
    }

    public String getSerialNumber() { return serialNumber; }
    public Integer getRamGb() { return ramGb; }
}
~~~

~~~java
package com.example.assets;

import jakarta.persistence.*;

@Entity
@DiscriminatorValue("VEHICLE")
public class Vehicle extends Asset {

    @Column(name = "vin", length = 32)
    private String vin;

    @Column(name = "seat_count")
    private Integer seatCount;

    protected Vehicle() {}

    public Vehicle(
        String assetCode,
        String displayName,
        String vin,
        Integer seatCount
    ) {
        super(assetCode, displayName);
        this.vin = vin;
        this.seatCount = seatCount;
    }

    public String getVin() { return vin; }
    public Integer getSeatCount() { return seatCount; }
}
~~~

Đây là **một mô hình ví dụ**, không phải yêu cầu mọi hệ phải dùng sequence. Nếu DB không hỗ trợ sequence native, cần chọn generator phù hợp provider và schema. Khi chuyển sang JOINED hoặc TABLE_PER_CLASS ở các phần sau, các ví dụ là **phương án mapping thay thế**, không được áp dụng đồng thời những annotation chiến lược lên cùng một hệ entity.

## 3. SINGLE_TABLE: một bảng, ít JOIN nhưng cột riêng subtype thường nullable

Với **@Inheritance(strategy = InheritanceType.SINGLE_TABLE)**, các trường của Asset, Laptop và Vehicle được trải vào **cùng bảng assets**. Cột discriminator **asset_type** dùng để xác định hàng thuộc lớp con nào.

Schema PostgreSQL minh họa:

~~~sql
CREATE SEQUENCE asset_id_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_type VARCHAR(20) NOT NULL,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    version BIGINT NOT NULL,
    serial_number VARCHAR(80),
    ram_gb INTEGER,
    vin VARCHAR(32),
    seat_count INTEGER
);
~~~

Một vài hàng:

| id | asset_type | asset_code | serial_number | ram_gb | vin | seat_count |
|---:|---|---|---|---:|---|---:|
| 1 | LAPTOP | LT-001 | SN-100 | 16 | NULL | NULL |
| 2 | VEHICLE | VH-001 | NULL | NULL | VIN-900 | 5 |
| 3 | LAPTOP | LT-002 | SN-101 | 32 | NULL | NULL |

### 3.1. Vì sao không thể đặt NOT NULL đơn giản trên tất cả subtype column?

Laptop bắt buộc có serialNumber, nhưng hàng Vehicle **không có serialNumber**. Nếu đặt **serial_number VARCHAR(80) NOT NULL** trên toàn bảng, mọi Vehicle sẽ vi phạm constraint. Điều tương tự xảy ra với vin của Vehicle khi lưu Laptop.

Đây là một hạn chế cấu trúc của SINGLE_TABLE: một constraint NOT NULL thông thường áp dụng lên **mọi hàng**, trong khi một thuộc tính lớp con chỉ có ý nghĩa với **một nhóm hàng**.

Trong Java, lập trình viên có thể viết:

~~~java
@Basic(optional = false)
@Column(name = "serial_number")
private String serialNumber;
~~~

Nhưng yêu cầu một subtype không được null **không tự biến thành NOT NULL vật lý hợp lệ cho toàn bảng**. Cách provider kiểm tra mapping và sinh DDL khác nhau; nếu cố dùng **@Column(nullable = false)** trên trường subtype SINGLE_TABLE, DDL tạo NOT NULL toàn cột có thể gây lỗi khi INSERT subtype khác hoặc provider có thể xử lý riêng. Phải xem DDL thật, không dựa vào annotation như bằng chứng rằng DB đã cưỡng chế ràng buộc đúng ý.

### 3.2. CHECK constraint theo discriminator

Nếu DBMS hỗ trợ CHECK phù hợp, có thể diễn đạt ràng buộc phụ thuộc loại:

~~~sql
ALTER TABLE assets
ADD CONSTRAINT ck_asset_subtype_fields
CHECK (
    (
        asset_type = 'LAPTOP'
        AND serial_number IS NOT NULL
        AND ram_gb IS NOT NULL
        AND ram_gb > 0
        AND vin IS NULL
        AND seat_count IS NULL
    )
    OR
    (
        asset_type = 'VEHICLE'
        AND vin IS NOT NULL
        AND seat_count IS NOT NULL
        AND seat_count > 0
        AND serial_number IS NULL
        AND ram_gb IS NULL
    )
);
~~~

Ví dụ CHECK vừa kiểm tra **bắt buộc có trường của loại mình** vừa cấm trường của loại khác. Nếu nghiệp vụ cho phép lưu tạm dữ liệu thiếu thông tin hoặc hệ phân cấp có thêm subtype, cần thay đổi biểu thức. Trong DBMS khác, tính năng CHECK, ngữ nghĩa NULL và cách thực thi có thể khác, nên phải kiểm tra phiên bản hệ quản trị.

**Ràng buộc qua discriminator là một cách khắc phục có điều kiện, không phải khả năng NOT NULL chuyên biệt sẵn có trên mỗi subtype trong schema một bảng.** Khi thêm một lớp con mới, phải cập nhật CHECK, index, dữ liệu và migration để không chặn những INSERT hợp lệ.

### 3.3. UNIQUE và FOREIGN KEY ở SINGLE_TABLE

Cột **asset_code** nằm trong một bảng nên có thể tạo UNIQUE toàn hệ phân cấp tương đối trực tiếp:

~~~sql
ALTER TABLE assets
ADD CONSTRAINT uq_asset_code UNIQUE (asset_code);
~~~

Một bảng **maintenance_records** muốn tham chiếu bất kỳ Asset nào có thể tạo một khóa ngoại duy nhất tới **assets(id)**:

~~~sql
CREATE TABLE maintenance_records (
    id BIGINT PRIMARY KEY,
    asset_id BIGINT NOT NULL REFERENCES assets(id),
    note VARCHAR(250)
);
~~~

Đó là lợi thế rõ của SINGLE_TABLE khi ứng dụng cần nhiều quan hệ tới base entity.

Với subtype-specific uniqueness như serialNumber của Laptop, có thể tạo UNIQUE(serial_number), nhưng cần xét cách DB xử lý **nhiều NULL**. Trong PostgreSQL, một unique index bình thường cho phép nhiều NULL; trên các hệ khác, quy tắc có thể khác. Nếu cần unique chỉ trong Laptop, một số DB cho phép **partial/filtered unique index**, ví dụ PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_laptop_serial
ON assets (serial_number)
WHERE asset_type = 'LAPTOP';
~~~

Đây là giải pháp phụ thuộc DBMS. Nếu uniqueness bao gồm nhiều tenant hoặc trạng thái, điều kiện index cần phản ánh chính xác phạm vi nghiệp vụ.

### 3.4. Chi phí truy vấn của SINGLE_TABLE

Một truy vấn đa hình:

~~~java
List<Asset> all = em.createQuery(
    "select a from Asset a order by a.assetCode",
    Asset.class
).getResultList();
~~~

Provider có thể dịch thành câu SELECT từ **một bảng** với các cột cần thiết và discriminator:

~~~sql
-- SQL minh họa, không cam kết giống một provider cụ thể.
SELECT id, asset_type, asset_code, display_name,
       serial_number, ram_gb, vin, seat_count
FROM assets
ORDER BY asset_code;
~~~

Để tải một subtype cụ thể:

~~~java
List<Laptop> laptops = em.createQuery(
    "select l from Laptop l where l.ramGb >= :minRam",
    Laptop.class
).setParameter("minRam", 16)
 .getResultList();
~~~

SQL điển hình lọc theo discriminator và cột lớp con trong cùng bảng:

~~~sql
SELECT *
FROM assets
WHERE asset_type = 'LAPTOP'
  AND ram_gb >= 16;
~~~

**Không cần JOIN cha–con** chỉ để lấy dữ liệu của Laptop, vì tất cả dữ liệu nằm trong một hàng.

Tuy nhiên, một bảng lớn có nhiều subtype và hàng chục cột hiếm khi dùng có thể làm bản ghi rộng, nhiều giá trị NULL, giảm mật độ hàng trên trang lưu trữ hoặc làm tăng I/O của một số truy vấn. DBMS có cách biểu diễn NULL và nén dữ liệu khác nhau; không nên kết luận mọi cột nullable đều tốn đúng kích thước tối đa. Vẫn cần đo với số lượng subtype, cấu trúc index và dữ liệu thực tế.

### 3.5. Chi phí ghi dữ liệu

INSERT một Laptop thường cần **một INSERT vào bảng assets** (ngoài thao tác cấp ID nếu có). Không phải ghi riêng bảng cha rồi bảng con. UPDATE thuộc tính chung và thuộc tính riêng đều đụng cùng bảng, đơn giản về số bảng, nhưng khi bảng rất lớn các index và lock trên một bảng trung tâm có thể trở thành điểm tập trung tải.

Nếu hệ thống có hàng chục subtype tăng theo thời gian, mỗi subtype mới thường yêu cầu **thêm cột vào bảng chung** và cập nhật CHECK/index. Đây cũng là chi phí migration cần đưa vào đánh giá.

## 4. JOINED: ràng buộc lớp con tốt hơn, đổi lấy JOIN

Với **@Inheritance(strategy = InheritanceType.JOINED)**, các thuộc tính chung nằm trong bảng cha và thuộc tính riêng nằm ở bảng con. Bảng con có PRIMARY KEY đồng thời là FOREIGN KEY tham chiếu bảng cha.

Mapping minh họa của phương án **thay thế**:

~~~java
@Entity
@Table(name = "assets")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Asset {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "asset_id_generator")
    @SequenceGenerator(
        name = "asset_id_generator",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, unique = true)
    private String assetCode;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Asset() {}
}

@Entity
@Table(name = "laptop_assets")
@PrimaryKeyJoinColumn(name = "id")
public class Laptop extends Asset {
    @Column(name = "serial_number", nullable = false)
    private String serialNumber;
    @Column(name = "ram_gb", nullable = false)
    private int ramGb;
    protected Laptop() {}
}

@Entity
@Table(name = "vehicle_assets")
@PrimaryKeyJoinColumn(name = "id")
public class Vehicle extends Asset {
    @Column(name = "vin", nullable = false)
    private String vin;
    @Column(name = "seat_count", nullable = false)
    private int seatCount;
    protected Vehicle() {}
}
~~~

Đoạn mapping rút gọn tập trung vào hình dạng JOINED, không phải phần code ghép chung với phương án SINGLE_TABLE. Các yêu cầu constructor, tạo đối tượng, validation và toàn bộ import cần được bổ sung khi dùng như một chương trình hoàn chỉnh.

### 4.1. Schema minh họa

~~~sql
CREATE TABLE assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE laptop_assets (
    id BIGINT PRIMARY KEY REFERENCES assets(id),
    serial_number VARCHAR(80) NOT NULL UNIQUE,
    ram_gb INTEGER NOT NULL CHECK (ram_gb > 0)
);

CREATE TABLE vehicle_assets (
    id BIGINT PRIMARY KEY REFERENCES assets(id),
    vin VARCHAR(32) NOT NULL UNIQUE,
    seat_count INTEGER NOT NULL CHECK (seat_count > 0)
);
~~~

Đặc điểm quan trọng:

- **assets** chứa các cột dùng chung và unique assetCode trên toàn hệ phân cấp.
- **laptop_assets** chỉ có hàng Laptop, nên **serial_number NOT NULL** là ràng buộc hợp lệ và có ý nghĩa trên tất cả các hàng của bảng này.
- **vehicle_assets** chỉ có hàng Vehicle, nên **vin NOT NULL** cũng đơn giản.
- Khóa **laptop_assets.id** và **vehicle_assets.id** tham chiếu id của assets; các bảng con không cấp ID độc lập.
- Muốn tìm cả dữ liệu chung và riêng của Laptop, ORM thường cần JOIN giữa assets và laptop_assets.

Chú ý một giới hạn của ràng buộc: FOREIGN KEY từ bảng con về bảng cha bảo đảm **không có hàng con mồ côi**, nhưng bản thân những FK đó **không bảo đảm mỗi hàng assets phải có đúng một hàng trong một bảng con**. Sự nhất quán về subtype thường do ORM/lifecycle và thiết kế DB bổ sung đảm nhiệm. Nếu nhiều ứng dụng ghi SQL trực tiếp, cần xem có cần discriminator, trigger, constraint hoặc quy trình kiểm tra riêng để cấm trạng thái “hàng cha không có subtype” và “một ID nằm ở hai subtype” hay không.

### 4.2. Đếm JOIN khi tải đúng một subtype

SQL điển hình để lấy Laptop:

~~~sql
SELECT a.id, a.asset_code, a.display_name,
       l.serial_number, l.ram_gb
FROM assets a
JOIN laptop_assets l ON l.id = a.id
WHERE a.id = 10;
~~~

Với cây kế thừa hai tầng như ví dụ, cần **một JOIN giữa bảng cha và bảng Laptop** để có đủ các thuộc tính. Nếu Laptop còn kế thừa một lớp trung gian entity và mỗi tầng được ánh xạ thành bảng riêng, số JOIN có thể tăng theo số tầng bảng cần tải.

Lưu ý: **số JOIN là tính chất của SQL thật được sinh cho từng truy vấn**, không phải một con số bắt buộc cố định của annotation JOINED. Nếu chỉ chọn những cột chung từ bảng cha, provider hoặc SQL thủ công có thể không cần JOIN tới tất cả bảng con.

### 4.3. Truy vấn đa hình thường tốn JOIN hơn

JPQL:

~~~java
List<Asset> assets = em.createQuery(
    "select a from Asset a order by a.assetCode",
    Asset.class
).getResultList();
~~~

Nếu cần dựng đầy đủ các object Laptop và Vehicle từ một kết quả đa hình, một SQL khả dĩ:

~~~sql
SELECT a.id, a.asset_code, a.display_name,
       l.id AS laptop_id, l.serial_number, l.ram_gb,
       v.id AS vehicle_id, v.vin, v.seat_count
FROM assets a
LEFT JOIN laptop_assets l ON l.id = a.id
LEFT JOIN vehicle_assets v ON v.id = a.id
ORDER BY a.asset_code;
~~~

Đây là **SQL minh họa**. Hibernate và EclipseLink có thể dùng discriminator, LEFT JOIN, truy vấn bổ sung hoặc chiến lược materialization khác nhau theo phiên bản và fetch plan. Khi có **n** bảng subtype, một truy vấn đa hình cần materialize mọi kiểu có thể có tới **n nhánh LEFT JOIN**, ngoài những join khác. Với nhiều mức kế thừa và nhiều quan hệ, SQL có thể phức tạp hơn đáng kể.

Nhưng không được mặc định một ứng dụng chỉ cần danh sách assetCode cũng phải join mọi subtype. **Projection** chọn cột chung có thể tránh join subtype:

~~~java
List<Object[]> rows = em.createQuery(
    "select a.id, a.assetCode from Asset a",
    Object[].class
).getResultList();
~~~

Tùy mapping và provider, truy vấn chỉ lấy thuộc tính của base entity có thể giảm lượng dữ liệu và JOIN, vì không cần dựng toàn bộ object subtype. Khi hiệu năng quan trọng, nên dùng DTO projection với kiểu rõ ràng thay vì tự tạo mọi entity chỉ để đọc hai trường.

### 4.4. Chi phí INSERT/UPDATE/DELETE

Tạo một Laptop mới thường liên quan ít nhất:

1. Lấy hoặc cấp ID phù hợp.
2. INSERT hàng **assets**.
3. INSERT hàng **laptop_assets** dùng chung ID.

Việc commit transaction giúp các thao tác của một entity không để lại dữ liệu thiếu một nửa khi thực hiện qua JPA đúng cách. Tuy nhiên, có thêm statement, FK check và index write so với một INSERT SINGLE_TABLE. Xóa một entity con cũng phải bảo đảm thứ tự thao tác phù hợp với FK.

UPDATE chỉ trường lớp con có thể chỉ đụng bảng con; UPDATE chỉ trường lớp cha có thể chỉ đụng bảng cha, tùy SQL strategy của provider. Đây có thể là lợi ích so với một bảng SINGLE_TABLE rất rộng nhưng cần kiểm tra SQL thực tế, đặc biệt khi provider cập nhật nhiều cột hoặc có optimistic locking.

### 4.5. Lợi ích về quản trị schema

JOINED phù hợp khi:

- Mỗi subtype có nhiều cột bắt buộc và nhiều CHECK/UNIQUE riêng.
- Dữ liệu subtype lớn, không muốn làm bảng cha rất rộng.
- Các nhóm có thể có tần suất thay đổi khác nhau.
- Cần khóa ngoại chung tới Asset, giữ được root table và identity toàn hệ.
- Truy vấn thường chỉ một subtype hoặc có thể dùng projection cho màn hình danh sách.

Đổi lại, đọc đầy đủ thông tin subtype thường cần JOIN và INSERT trải qua nhiều bảng.

## 5. TABLE_PER_CLASS: đọc subtype riêng thuận tiện, truy vấn đa hình có thể dùng UNION

Trong **@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)**, mỗi entity concrete có bảng riêng chứa cả những cột của lớp cha và cột riêng của lớp đó. Với Asset là lớp trừu tượng, có thể chỉ có bảng **laptop_assets** và **vehicle_assets**, không nhất thiết có một bảng assets vật lý dùng chung.

Mapping minh họa cho **một cấu hình thay thế**, không chạy đồng thời với các ví dụ trước:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Asset {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "asset_id_generator")
    @SequenceGenerator(
        name = "asset_id_generator",
        sequenceName = "asset_id_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "asset_code", nullable = false, length = 40)
    private String assetCode;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    protected Asset() {}
}

@Entity
@Table(name = "laptop_assets")
public class Laptop extends Asset {
    @Column(name = "serial_number", nullable = false)
    private String serialNumber;
    @Column(name = "ram_gb", nullable = false)
    private int ramGb;
    protected Laptop() {}
}

@Entity
@Table(name = "vehicle_assets")
public class Vehicle extends Asset {
    @Column(name = "vin", nullable = false)
    private String vin;
    @Column(name = "seat_count", nullable = false)
    private int seatCount;
    protected Vehicle() {}
}
~~~

Tất cả subtype dùng chung generator để tránh cấp trùng ID giữa các bảng. Việc dùng SEQUENCE ở đây phù hợp với PostgreSQL, Oracle và các DB/provider có hỗ trợ; **không giả định IDENTITY độc lập của từng bảng sẽ an toàn để nhận diện entity đa hình**. Với TABLE_PER_CLASS, việc bảo đảm không đụng ID giữa các bảng là một yêu cầu thiết kế quan trọng, nhất là khi ứng dụng tham chiếu bằng ID của lớp cha.

### 5.1. Schema minh họa

~~~sql
CREATE TABLE laptop_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    serial_number VARCHAR(80) NOT NULL UNIQUE,
    ram_gb INTEGER NOT NULL CHECK (ram_gb > 0)
);

CREATE TABLE vehicle_assets (
    id BIGINT PRIMARY KEY,
    asset_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    vin VARCHAR(32) NOT NULL UNIQUE,
    seat_count INTEGER NOT NULL CHECK (seat_count > 0)
);
~~~

Đây là hai bảng độc lập. Mỗi bảng chứa những cột chung như asset_code và display_name, tức **mapping được dùng lại nhưng cột vật lý bị lặp**.

Lợi ích:

- Cột riêng subtype có thể được khai báo **NOT NULL, CHECK, UNIQUE** một cách trực tiếp.
- Truy vấn chỉ Laptop có thể đọc **một bảng laptop_assets**, không phải JOIN bảng cha.
- Các bảng không có nhiều cột nullable không liên quan đến subtype.

Chi phí:

- Định nghĩa cột chung phải được duy trì trên nhiều bảng.
- UNIQUE(asset_code) trong từng bảng **không bảo đảm unique giữa Laptop và Vehicle**.
- Truy vấn Asset đa hình thường cần **UNION/UNION ALL** giữa các bảng concrete.
- Không có một bảng Asset vật lý chung để một khóa ngoại SQL đơn giản tham chiếu mọi subtype.

### 5.2. Global uniqueness trở nên khó hơn

Trong bảng laptop_assets, unique(asset_code) chỉ ngăn hai Laptop cùng mã. Trong vehicle_assets, unique(asset_code) chỉ ngăn hai Vehicle cùng mã. Database vẫn có thể chứa:

~~~text
laptop_assets  asset_code = "ASSET-100"
vehicle_assets asset_code = "ASSET-100"
~~~

Nếu domain yêu cầu assetCode duy nhất **trên toàn bộ hệ phân cấp**, hai UNIQUE constraint riêng lẻ là chưa đủ. Có thể cần:

- Một bảng đăng ký mã toàn cục riêng với unique constraint và quy trình ghi nhất quán.
- Một dịch vụ cấp mã có kiểm soát đồng thời, với constraint cuối cùng ở database.
- Thiết kế lại chiến lược dùng SINGLE_TABLE hoặc JOINED để có root table mang mã.

Không nên chỉ kiểm tra bằng SELECT trong cả hai bảng trước INSERT rồi kết luận không trùng: hai transaction đồng thời có thể cùng quan sát chưa có mã và cùng ghi vào hai bảng khác nhau.

### 5.3. Chi phí truy vấn subtype cụ thể

JPQL:

~~~java
List<Vehicle> vehicles = em.createQuery(
    "select v from Vehicle v where v.seatCount >= :minSeats",
    Vehicle.class
).setParameter("minSeats", 5)
 .getResultList();
~~~

SQL minh họa:

~~~sql
SELECT id, asset_code, display_name, vin, seat_count
FROM vehicle_assets
WHERE seat_count >= 5;
~~~

Vì mọi cột cần thiết nằm trong bảng Vehicle, **không có JOIN tới bảng Asset**. Với ứng dụng gần như luôn làm việc trực tiếp theo từng subtype, đây có thể là lợi thế.

### 5.4. Chi phí truy vấn đa hình: UNION

JPQL:

~~~java
List<Asset> all = em.createQuery(
    "select a from Asset a order by a.assetCode",
    Asset.class
).getResultList();
~~~

Vì không có bảng assets duy nhất, provider có thể tạo câu SQL mang ý tưởng như:

~~~sql
SELECT
    id, asset_code, display_name,
    serial_number, ram_gb,
    CAST(NULL AS VARCHAR(32)) AS vin,
    CAST(NULL AS INTEGER) AS seat_count,
    'LAPTOP' AS asset_type
FROM laptop_assets
UNION ALL
SELECT
    id, asset_code, display_name,
    CAST(NULL AS VARCHAR(80)) AS serial_number,
    CAST(NULL AS INTEGER) AS ram_gb,
    vin, seat_count,
    'VEHICLE' AS asset_type
FROM vehicle_assets;
~~~

Đây là **ví dụ hình dạng SQL**, không phải cam kết SQL chính xác Hibernate/EclipseLink sinh ra. Với ORDER BY trên toàn kết quả, provider có thể bao UNION trong truy vấn ngoài hoặc dùng cú pháp của DBMS.

Khi số subtype concrete tăng:

1. Số nhánh UNION có thể tăng.
2. DB có thể phải đọc nhiều bảng/index để trả về tất cả Asset.
3. Cần hợp nhất hoặc sắp xếp kết quả để phân trang và ORDER BY toàn hệ.
4. Các loại cột riêng phải được căn chỉnh trong kết quả UNION, thường dùng biểu thức NULL hoặc CAST.
5. Nếu truy vấn có điều kiện chỉ áp dụng một subtype, optimizer có thể lược bỏ nhánh khi điều kiện cho phép, nhưng không nên giả định mọi provider/DBMS đều tối ưu như nhau.

**UNION ALL** giữ các hàng của mỗi nhánh; **UNION** thông thường còn loại bản sao hoàn toàn theo các cột SELECT và có thể thêm chi phí. Việc provider dùng dạng nào và cách DB tối ưu là chi tiết phải quan sát bằng SQL log và execution plan.

### 5.5. Vấn đề khóa ngoại tới lớp cha

Một bảng **maintenance_records(asset_id)** muốn tham chiếu mọi Asset có thể dùng FK tới **assets(id)** khi có bảng root (SINGLE_TABLE/JOINED). Với TABLE_PER_CLASS không có bảng root vật lý chứa mọi ID, nên không có một đích FK SQL đơn giản cho mọi subtype.

Có thể thiết kế tham chiếu kiểu **(asset_type, asset_id)** và kiểm tra tính hợp lệ ở ứng dụng hoặc bằng các cấu trúc DB bổ sung, nhưng foreign key chuẩn không tự chọn bảng đích dựa vào asset_type. Các quan hệ JPA trỏ tới root entity có thể đòi SQL đa hình phức tạp và có giới hạn theo provider/dialect.

Do đó, nếu domain có nhiều quan hệ **@ManyToOne Asset** và cần database bảo vệ toàn vẹn tham chiếu trực tiếp, TABLE_PER_CLASS thường kém thuận lợi hơn SINGLE_TABLE hoặc JOINED.

## 6. @MappedSuperclass: dùng lại trường, không có truy vấn root đa hình

**@MappedSuperclass** không phải một chiến lược @Inheritance entity giống ba chiến lược trên. Nó cho phép lớp cha khai báo mapping chung, được sao chép vào bảng của từng entity kế thừa, nhưng bản thân lớp cha **không được quản lý như một entity độc lập**.

~~~java
@MappedSuperclass
public abstract class AssetBase {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String assetCode;

    @Column(nullable = false)
    private String displayName;
}

@Entity
@Table(name = "laptop_assets")
public class Laptop extends AssetBase {
    @Column(nullable = false)
    private String serialNumber;
}

@Entity
@Table(name = "vehicle_assets")
public class Vehicle extends AssetBase {
    @Column(nullable = false)
    private String vin;
}
~~~

Ví dụ rút gọn để minh họa phạm vi ánh xạ; khi dùng thực tế cần constructor thích hợp và getters/constructors nghiệp vụ. Các cột chung lặp trong laptop_assets và vehicle_assets, tương tự ý tưởng lưu riêng của TABLE_PER_CLASS.

Khác biệt quan trọng:

- **AssetBase không phải @Entity**, nên JPQL **select a from AssetBase a** không phải truy vấn entity root hợp lệ.
- Không thể dùng AssetBase làm entity target của một association JPA theo cách một @Entity root được dùng.
- Không có identity đa hình chung được JPA quản lý cho mọi subtype chỉ dựa trên @MappedSuperclass.
- Các bảng con có thể có ID và generator riêng; phải bảo vệ business uniqueness toàn hệ bằng phương án phù hợp nếu nghiệp vụ yêu cầu.

Nếu ứng dụng thực sự không cần tìm “mọi loại Asset” bằng một JPQL query và chỉ muốn dùng lại một vài trường chung, **@MappedSuperclass có thể đơn giản hơn** việc triển khai một hệ phân cấp entity đa hình.

## 7. So sánh ràng buộc cột giữa các chiến lược

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS | @MappedSuperclass |
|---|---|---|---|---|
| Bảng vật lý của root entity | Một bảng cho cả hệ | Có bảng root | Không bắt buộc có bảng cho root trừu tượng | Không có entity root |
| Cột chung | Một bản trong bảng chung | Một bản trong bảng root | Lặp ở các bảng subtype concrete | Lặp ở các bảng entity con |
| Cột chỉ của subtype | Trong bảng chung, thường nullable | Trong bảng subtype | Trong bảng subtype | Trong bảng entity con |
| NOT NULL của trường subtype | Khó áp dụng trực tiếp; thường cần CHECK theo discriminator | Dễ khai báo ở bảng subtype | Dễ khai báo ở bảng subtype | Dễ khai báo ở bảng con |
| CHECK/UNIQUE riêng subtype | Có thể cần CHECK/partial index phụ thuộc DB | Dễ đặt trên bảng subtype | Dễ đặt trên bảng subtype | Dễ đặt trên bảng con |
| UNIQUE trên cột chung toàn hệ | Đơn giản trên một bảng | Đơn giản ở root table | Không được bảo đảm bởi UNIQUE riêng mỗi bảng | Không tự được bảo đảm |
| FK từ bảng khác tới mọi subtype | Đơn giản qua bảng chung | Đơn giản qua bảng root | Khó có FK một bảng tới mọi subtype | Không có entity root làm đích |
| Ràng buộc “mỗi root đúng một subtype” | Discriminator + CHECK có thể hỗ trợ | Cần xem tính nhất quán hàng root/subtype | Mỗi hàng thuộc bảng subtype, nhưng ID toàn hệ cần kiểm soát | Không có root đa hình |
| Thay đổi schema khi thêm subtype | Thêm cột vào bảng chung | Thêm bảng subtype | Thêm bảng subtype và logic union | Thêm bảng entity con |

Đặc biệt, **ràng buộc ở Java** và **ràng buộc DB** là hai lớp khác nhau. Chẳng hạn @Basic(optional=false), @Column(nullable=false) và Bean Validation @NotNull có ý nghĩa riêng; database chỉ bảo vệ đúng khi DDL tương ứng thực sự tồn tại và được DB thực thi. Trong SINGLE_TABLE, thông tin trường bắt buộc của subtype rất dễ mất đi nếu chỉ nhìn @Column và không thiết kế CHECK thích hợp.

### 7.1. Bảng quyết định theo dạng constraint

**Ràng buộc chung của mọi entity:** Ví dụ assetCode bắt buộc và duy nhất toàn hệ. SINGLE_TABLE và JOINED thường dễ biểu diễn bằng NOT NULL/UNIQUE trên bảng chung. TABLE_PER_CLASS phải giải quyết uniqueness giữa nhiều bảng bằng thiết kế bổ sung.

**Ràng buộc chỉ một subtype:** Ví dụ Laptop.serialNumber bắt buộc. JOINED/TABLE_PER_CLASS và @MappedSuperclass dễ dùng NOT NULL ở bảng riêng; SINGLE_TABLE thường cần nullable vật lý kết hợp CHECK theo loại.

**Quan hệ FK từ entity ngoài tới mọi loại:** SINGLE_TABLE/JOINED có đích root table rõ ràng. TABLE_PER_CLASS và @MappedSuperclass phức tạp hơn nhiều hoặc không hỗ trợ truy cập root như một entity.

**Ràng buộc kết hợp nhiều subtype:** Ví dụ assetCode của Laptop không được trùng assetCode của Vehicle. Root table chung có lợi thế lớn; những bảng riêng cần bảng đăng ký mã toàn cục hoặc cơ chế điều phối khác.

## 8. So sánh số phép JOIN và UNION theo kiểu truy vấn

Không thể gắn một con số JOIN cố định cho mọi query của một inheritance strategy. Nhưng có thể lập mô hình kỳ vọng theo **loại dữ liệu cần lấy**.

| Tình huống | SINGLE_TABLE | JOINED | TABLE_PER_CLASS | @MappedSuperclass |
|---|---|---|---|---|
| Đọc một Laptop đầy đủ | Một bảng, không JOIN kế thừa | Thường JOIN root + bảng Laptop | Một bảng Laptop | Một bảng Laptop |
| Đọc một Vehicle đầy đủ | Một bảng, không JOIN kế thừa | Thường JOIN root + bảng Vehicle | Một bảng Vehicle | Một bảng Vehicle |
| Đọc danh sách Asset đa hình đầy đủ | Một bảng | Có thể LEFT JOIN nhiều subtype | Có thể UNION nhiều bảng concrete | Không truy vấn trực tiếp root |
| Chỉ lấy id/code thuộc tính chung | Một bảng | Có thể chỉ đọc root | Có thể cần UNION hoặc cách chọn nhánh | Query từng entity con |
| Lọc thuộc tính Laptop | Một bảng + điều kiện discriminator | JOIN root + Laptop nếu cần dữ liệu root | Một bảng Laptop | Một bảng Laptop |
| FK của entity ngoài tới mọi Asset | Một FK tới bảng chung | Một FK tới root | Không có bảng root chung | Không có entity root |
| INSERT Laptop | Một bảng nghiệp vụ | Hai bảng (root và Laptop) | Một bảng Laptop | Một bảng Laptop |

Khi nói **JOINED có nhiều JOIN**, cần phân biệt rõ:

- **JOIN do kế thừa:** nối các bảng class hierarchy để dựng một object.
- **JOIN do association:** nối Asset tới Owner, Department, MaintenanceRecord... Những JOIN này có thể xuất hiện ở bất kỳ chiến lược nào.
- **JOIN do fetch plan:** ORM có thể thêm JOIN do EAGER hoặc fetch join, dù không liên quan đến kế thừa.

Ví dụ một câu SQL có 6 JOIN không đồng nghĩa “JOINED tạo 6 JOIN”; trong đó có thể chỉ 1 hoặc 2 JOIN phục vụ inheritance, phần còn lại do quan hệ nghiệp vụ.

### 8.1. Ước lượng theo số subtype

Giả sử hệ phân cấp có **n = 8 lớp con concrete**, một query JPQL tải đầy đủ mọi Asset:

- SINGLE_TABLE có thể đọc một bảng chứa toàn bộ cột.
- JOINED có thể cần nhiều nhánh LEFT JOIN để xác định và tải trường cụ thể của subtype.
- TABLE_PER_CLASS có thể cần UNION giữa nhiều bảng concrete.
- @MappedSuperclass không cho phép truy vấn AssetBase như một entity root; ứng dụng phải truy vấn từng loại hoặc tạo một API hợp nhất ở tầng khác.

Nhưng **8 JOIN** không đồng nghĩa chắc chắn chậm hơn **8 nhánh UNION**. Chi phí phụ thuộc kích thước bảng, index, số hàng mỗi subtype, selectivity, dạng projection, cache, cách provider sinh SQL và optimizer DB.

### 8.2. Chi phí của cây kế thừa sâu

Nếu có Asset → Vehicle → ElectricVehicle → ElectricTruck và mỗi tầng có một bảng khi dùng JOINED, một object ElectricTruck đầy đủ có thể cần nối dữ liệu qua nhiều tầng. Khi cây sâu, số JOIN theo đường thừa kế tăng, nhưng đổi lại những constraint và cột của từng tầng được tách rõ.

Với SINGLE_TABLE, toàn bộ trường của các tầng vẫn nằm trong một hàng; với TABLE_PER_CLASS, mỗi bảng concrete chứa cột của các tầng, khiến việc thêm một trường chung ở lớp cha có thể đòi sửa nhiều bảng.

## 9. Đánh giá chi phí truy vấn: đếm JOIN chưa đủ

Hai câu SQL có số JOIN bằng nhau chưa chắc tốn thời gian bằng nhau. Hệ quản trị phải xử lý:

- **Số hàng đầu vào:** bao nhiêu Asset, bao nhiêu Laptop, Vehicle.
- **Selectivity:** bộ lọc loại bỏ được bao nhiêu hàng.
- **Độ rộng hàng:** câu SELECT mang theo bao nhiêu cột, byte, kiểu dữ liệu lớn.
- **Index:** có index tương ứng với WHERE, JOIN và ORDER BY không.
- **Cardinality ước lượng:** optimizer dự đoán đúng số hàng cho từng bước không.
- **Thuật toán JOIN:** nested loop, hash join, merge join tùy DBMS và kích thước dữ liệu.
- **Sort/materialization:** truy vấn đa hình có cần sắp xếp, ghi bộ nhớ tạm hoặc spill ra đĩa không.
- **Dữ liệu nằm trong cache hay cần I/O:** cold-cache và warm-cache có thể khác nhau rõ.
- **Network/JDBC:** tổng số dòng và tổng byte truyền từ DB đến ứng dụng.
- **ORM hydration:** chi phí dựng entity, proxy, persistence context và dirty checking.

Một query SINGLE_TABLE lấy mọi cột của một bảng rất rộng có thể truyền nhiều dữ liệu không cần thiết. Ngược lại, một query JOINED nối bảng root nhỏ với đúng bảng subtype có index phù hợp có thể rất nhanh. Một truy vấn UNION của TABLE_PER_CLASS trên nhiều bảng nhỏ có thể nhanh hơn một truy vấn JOINED phức tạp, nhưng nếu phải ORDER BY và phân trang trên tất cả bảng lớn, UNION có thể tốn nhiều tài nguyên.

### 9.1. Phân loại workload trước khi chọn chiến lược

Nên thống kê ít nhất những nhóm truy vấn:

| Nhóm | Ví dụ nghiệp vụ | Thuộc tính quan trọng |
|---|---|---|
| **Danh sách đa hình** | Màn hình tổng hợp mọi Asset | Tần suất cao, chỉ vài cột chung |
| **Chi tiết subtype** | Xem một Laptop có RAM/serial | Tải một subtype đầy đủ |
| **Lọc theo subtype** | Tìm tất cả Laptop có RAM từ 32 GB | Index subtype, selectivity |
| **Quan hệ đến root** | Mỗi maintenance record tham chiếu một Asset | FK và khả năng đọc Asset qua association |
| **Thống kê toàn hệ** | Đếm Asset theo loại, trạng thái | Có thể tận dụng discriminator/root |
| **Ghi nhiều** | Nhập hàng nghìn tài sản | Số INSERT, FK checks, batching |
| **Cập nhật riêng subtype** | Đổi VIN hoặc serial | Cập nhật một bảng hay bảng rất rộng |
| **Phân trang theo loại** | Trang 20 của danh sách tất cả tài sản | ORDER BY, LIMIT/OFFSET hoặc keyset pagination |

Nếu 95% use case chỉ đọc Laptop, việc tối ưu query Asset đa hình không nhất thiết là ưu tiên. Nếu sản phẩm cung cấp API chung tìm mọi tài sản theo assetCode và hàng chục entity tham chiếu Asset, root table ổn định và global uniqueness có thể quan trọng hơn việc tiết kiệm một JOIN.

## 10. So sánh những query cụ thể

### 10.1. Query A — chỉ lấy trường chung

~~~java
List<Object[]> rows = em.createQuery(
    "select a.id, a.assetCode, a.displayName " +
    "from Asset a order by a.assetCode",
    Object[].class
).getResultList();
~~~

Khi chỉ lấy thuộc tính chung:

- **SINGLE_TABLE:** đọc các cột chung từ assets, không phải JOIN hierarchy.
- **JOINED:** có cơ hội đọc từ root assets mà không phải materialize subtype. Provider vẫn có thể thêm join hoặc discriminator logic tùy query/implementation; phải xem SQL thật.
- **TABLE_PER_CLASS:** có thể phải quét nhiều bảng concrete qua UNION để tạo danh sách đủ mọi loại.
- **@MappedSuperclass:** không có truy vấn root tương đương. Có thể lập báo cáo bằng native SQL UNION hoặc truy vấn các loại rồi tổng hợp, nhưng đó không còn là một entity root query theo chuẩn JPA.

Vì dữ liệu API chỉ dùng ba trường, **DTO projection** thường phù hợp hơn tải đầy đủ entity và mọi cột subtype:

~~~java
public record AssetSummary(Long id, String code, String name) {}

List<AssetSummary> summaries = em.createQuery(
    "select new com.example.assets.AssetSummary(" +
    "a.id, a.assetCode, a.displayName) " +
    "from Asset a order by a.assetCode",
    AssetSummary.class
).getResultList();
~~~

Đoạn trên giả định record AssetSummary nằm trong đúng package được nêu và môi trường hỗ trợ Java record. DTO constructor expression là chức năng JPQL; nó không đòi hỏi tạo object entity với tất cả trường lớp con.

### 10.2. Query B — chỉ tìm Laptop

~~~java
List<Laptop> laptops = em.createQuery(
    "select l from Laptop l " +
    "where l.ramGb >= :minRam",
    Laptop.class
).setParameter("minRam", 32)
 .getResultList();
~~~

| Chiến lược | Hình dạng SQL có thể gặp |
|---|---|
| SINGLE_TABLE | SELECT từ assets với điều kiện asset_type = 'LAPTOP' và ram_gb |
| JOINED | JOIN assets và laptop_assets, lọc ram_gb ở bảng con |
| TABLE_PER_CLASS | SELECT từ laptop_assets |
| @MappedSuperclass | SELECT từ laptop_assets |

Nếu chỉ truy vấn subtype cụ thể, TABLE_PER_CLASS và @MappedSuperclass có thể tránh JOIN inheritance. Tuy nhiên, nếu truy vấn còn fetch owner, images và tags, số JOIN có thể vẫn lớn do association chứ không do inheritance.

### 10.3. Query C — truy vấn theo loại entity

Trong JPQL, **TYPE** có thể được dùng để kiểm tra loại entity thực tế:

~~~java
List<Asset> onlyLaptops = em.createQuery(
    "select a from Asset a where type(a) = Laptop",
    Asset.class
).getResultList();
~~~

Ngữ nghĩa JPQL là chỉ lấy những entity có kiểu Laptop; SQL tạo ra để xác định subtype tùy inheritance strategy:

- SINGLE_TABLE thường tận dụng discriminator.
- JOINED có thể dùng discriminator nếu có hoặc join/existence phù hợp.
- TABLE_PER_CLASS có thể chọn đúng nhánh subtype hoặc vẫn tạo SQL đa hình có bộ lọc, tùy provider.

Đừng cho rằng **TYPE(a)** luôn được provider biến thành một phép so sánh chuỗi rẻ như **asset_type = 'LAPTOP'**. Cần xem execution plan tương ứng.

### 10.4. Query D — dùng thuộc tính subtype trong truy vấn gốc

JPQL có cú pháp **TREAT** để diễn đạt thao tác nhìn một entity dưới dạng subtype:

~~~java
List<Asset> highRamAssets = em.createQuery(
    "select a from Asset a " +
    "where treat(a as Laptop).ramGb >= :minRam",
    Asset.class
).setParameter("minRam", 32)
 .getResultList();
~~~

Với SINGLE_TABLE, provider có thể lọc discriminator và ram_gb trên một bảng. Với JOINED, có thể phải JOIN laptop_assets. Với TABLE_PER_CLASS, có thể cần điều chỉnh nhánh UNION. TREAT làm rõ chủ đích truy vấn ở tầng JPQL, **không loại bỏ chi phí vật lý** do cách lưu trữ.

### 10.5. Query E — thống kê theo loại

Một truy vấn đếm mọi Asset:

~~~java
Long count = em.createQuery(
    "select count(a) from Asset a",
    Long.class
).getSingleResult();
~~~

SINGLE_TABLE và JOINED có thể đếm từ bảng root/chung nếu mapping và optimizer cho phép. TABLE_PER_CLASS có thể phải hợp nhất số lượng từ nhiều bảng, hoặc provider có thể dùng UNION/aggregation theo cách riêng. Nếu thống kê thường xuyên trên dữ liệu lớn, có thể cần summary table, materialized view hoặc pipeline báo cáo độc lập; không nên giả định mọi phép đếm phải materialize từng entity.

### 10.6. Query F — phân trang danh sách đa hình

~~~java
List<Asset> page = em.createQuery(
    "select a from Asset a order by a.assetCode",
    Asset.class
).setFirstResult(100)
 .setMaxResults(20)
 .getResultList();
~~~

SINGLE_TABLE thường có điều kiện phân trang/sắp xếp trên một bảng. JOINED có thể phân trang trên root nhưng khi dựng đầy đủ subtype cần join. TABLE_PER_CLASS có thể đòi hợp nhất rồi **sắp xếp trên tập hợp nhiều bảng**, gây chi phí cao hơn so với chỉ đọc một subtype.

Nếu danh sách được phân trang trên tập rất lớn, phân trang bằng OFFSET có thể kém hiệu quả ở trang sâu bất kể chiến lược. Có thể xem xét **keyset pagination** với một sort key duy nhất, ổn định; khi dùng TABLE_PER_CLASS phải đảm bảo sort key và cách tổng hợp nhiều bảng tương thích.

## 11. Thiết kế index theo hình dạng lưu trữ

### 11.1. SINGLE_TABLE

Các query thường gặp:

~~~sql
SELECT id, asset_code, display_name
FROM assets
WHERE asset_type = 'LAPTOP'
ORDER BY asset_code;
~~~

Có thể cân nhắc index có thành phần discriminator và sort/filter column:

~~~sql
CREATE INDEX ix_assets_type_code
ON assets (asset_type, asset_code);
~~~

Với dữ liệu Laptop và filter RAM, trong PostgreSQL có thể cân nhắc partial index:

~~~sql
CREATE INDEX ix_laptop_ram
ON assets (ram_gb)
WHERE asset_type = 'LAPTOP';
~~~

Nhưng nếu bảng chỉ vài nghìn hàng và RAM có selectivity thấp, index thêm có thể không được dùng hoặc tăng chi phí ghi nhiều hơn lợi ích đọc. Cần xem execution plan và workload thay vì tạo index cho mọi cột.

### 11.2. JOINED

Ở JOINED, **assets.id** và **laptop_assets.id** thường có index vì là PRIMARY KEY. Một query join theo ID có đường truy cập rõ ràng:

~~~sql
SELECT a.id, a.asset_code, l.ram_gb
FROM assets a
JOIN laptop_assets l ON l.id = a.id
WHERE l.ram_gb >= 32;
~~~

Nếu ram_gb có khả năng lọc mạnh, có thể thêm index trên **laptop_assets(ram_gb)**. Optimizer có thể bắt đầu từ những Laptop phù hợp rồi join về assets theo id. Ngược lại, nếu tìm đúng assetCode duy nhất, optimizer có thể tìm một hàng assets qua unique index rồi join laptop_assets bằng PK.

**Không có nghĩa mỗi JOIN phải tạo thêm một index mới**: nhiều cột nối đã được index do PRIMARY KEY. Bước quan trọng là xem DB chọn đường đi dựa trên điều kiện lọc nào.

### 11.3. TABLE_PER_CLASS

Vì các cột chung lặp ở nhiều bảng, có thể cần index tương tự trên mỗi bảng:

~~~sql
CREATE INDEX ix_laptop_asset_code ON laptop_assets(asset_code);
CREATE INDEX ix_vehicle_asset_code ON vehicle_assets(asset_code);
~~~

Nếu mỗi bảng đã có UNIQUE(asset_code), DB thường có index tương ứng và các index thường trên chỉ là minh họa **không nên tạo trùng lặp vô ích**. Khi dùng TABLE_PER_CLASS, phải quản lý cấu trúc index cho từng subtype, nhưng một index trên laptop_assets không thể giúp trực tiếp đọc hàng vehicle_assets.

### 11.4. Không dùng index để thay thế constraint nghiệp vụ

Một index thông thường giúp truy vấn nhưng **không cấm dữ liệu trùng**. Nếu assetCode cần duy nhất, phải có UNIQUE constraint/unique index theo semantics phù hợp. Với TABLE_PER_CLASS, UNIQUE trên mỗi bảng không bảo đảm unique xuyên bảng; cần một cơ chế toàn cục khác.

## 12. Đo hiệu năng bằng SQL thực tế thay vì dự đoán

Quy trình thực nghiệm hữu ích:

1. **Chốt câu hỏi nghiệp vụ** cần tối ưu: danh sách Asset, chi tiết Laptop, query từ MaintenanceRecord...
2. **Tạo dữ liệu đại diện**: số Asset, tỉ lệ các subtype, số lớp kế thừa, độ dài cột, phân bố bộ lọc.
3. **Giữ cùng môi trường**: phiên bản DBMS, provider, JDBC driver, pool, index và cấu hình tương thích.
4. **Bật SQL logging có kiểm soát**: thu đúng câu SQL mà provider thực thi.
5. **Chạy EXPLAIN/EXPLAIN ANALYZE** tùy hệ quản trị để xem execution plan, hàng đọc, join/scan, sort và I/O.
6. **Đo end-to-end**: thời gian từ service, số round-trip SQL, kích thước response, lượng object entity và query phát sinh do lazy loading.
7. **Lặp lại dưới tải đại diện**: đọc nóng/lạnh, số concurrent requests, phân trang và transaction write.
8. **Ghi lại trade-off**: không chỉ median latency mà còn p95/p99, CPU, bộ nhớ và kế hoạch migration.

### 12.1. Ví dụ EXPLAIN ANALYZE trên PostgreSQL

Với SINGLE_TABLE:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, asset_code, display_name
FROM assets
WHERE asset_type = 'LAPTOP'
ORDER BY asset_code
LIMIT 20;
~~~

Với JOINED:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.id, a.asset_code, a.display_name, l.ram_gb
FROM assets a
JOIN laptop_assets l ON l.id = a.id
WHERE l.ram_gb >= 32
ORDER BY a.asset_code
LIMIT 20;
~~~

Với TABLE_PER_CLASS, có thể đo query UNION điển hình:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, asset_code, display_name, asset_type
FROM (
    SELECT id, asset_code, display_name,
           'LAPTOP' AS asset_type
    FROM laptop_assets
    UNION ALL
    SELECT id, asset_code, display_name,
           'VEHICLE' AS asset_type
    FROM vehicle_assets
) AS combined_assets
ORDER BY asset_code
LIMIT 20;
~~~

Ba câu truy vấn chỉ để minh họa cách kiểm tra **ba dạng SQL**; chúng không tương đương hoàn toàn về tất cả trường và bộ lọc. Khi benchmark cần dùng **các truy vấn có kết quả và yêu cầu dữ liệu tương đương**, cùng dataset thích hợp, để so sánh công bằng.

**EXPLAIN ANALYZE thực thi câu SELECT** và đo trên môi trường hiện tại; nên chạy tại dev/staging thay vì vô tư thử query nặng trên production. Đối với truy vấn ghi, EXPLAIN ANALYZE có thể thực sự thay đổi dữ liệu, cần transaction rollback hoặc môi trường thử riêng theo DBMS.

### 12.2. Đọc execution plan như thế nào?

Các dấu hiệu đáng xem:

- **Sequential scan:** có phải đọc hầu hết bảng không? Nếu truy vấn vốn lấy gần tất cả hàng, sequential scan có thể hợp lý.
- **Index scan:** DB có tận dụng index phù hợp với filter/sort không?
- **Nested loop:** vòng lặp join có khiến số lần truy cập bảng con tăng mạnh không?
- **Hash join:** có tạo bảng hash lớn hoặc spill ra đĩa không?
- **Sort:** sắp xếp bao nhiêu hàng trước LIMIT/OFFSET, có dùng bộ nhớ tạm quá nhiều không?
- **Append/Union:** TABLE_PER_CLASS có đọc những nhánh không cần thiết không?
- **Rows estimated vs actual:** thống kê DB có phản ánh phân bố dữ liệu subtype đúng không?
- **Buffers và I/O:** query chậm do CPU, đọc nhiều page hay chờ storage?

Không có một toán tử nào luôn xấu. Cần xem **khối lượng dữ liệu và kết quả thực tế**, không chỉ đếm số từ JOIN trong SQL.

### 12.3. Phân biệt JOIN inheritance với N+1 queries

Ví dụ một truy vấn Asset trả 100 tài sản, rồi ứng dụng gọi **asset.getOwner().getName()** cho từng tài sản. Nếu association owner là LAZY và chưa tải, provider có thể chạy thêm nhiều SELECT. Đây là vấn đề **N+1** do cách lấy quan hệ, không đồng nghĩa với chi phí JOINED inheritance.

Vì vậy khi đo:

- Ghi số statement và hình dạng SQL của **truy vấn gốc**.
- Ghi các statement **truy vấn phát sinh khi duyệt association**.
- Xem fetch plan, entity graph hoặc projection trước khi kết luận chiến lược kế thừa gây tất cả vấn đề.

Ngay cả SINGLE_TABLE cũng có thể bị N+1 khi đọc association. Ngược lại, JOINED có thể chạy một truy vấn JOIN hợp lý mà không có N+1 nếu fetch plan được thiết kế đúng.

## 13. Lựa chọn strategy theo dữ liệu và yêu cầu ràng buộc

### 13.1. Khi SINGLE_TABLE thường phù hợp

- Hệ phân cấp có ít hoặc vừa subtype, không có quá nhiều trường riêng.
- Thường truy vấn tất cả subtype trong cùng màn hình hoặc API.
- Cần **một khóa chính và business key duy nhất** toàn hệ.
- Nhiều bảng ngoài tham chiếu root entity.
- Chấp nhận thiết kế CHECK/validation để bảo vệ các trường bắt buộc riêng subtype.
- Mục tiêu tối ưu là đọc đơn giản, ít JOIN inheritance.

**Điểm cần đánh đổi:** bảng rộng, nhiều NULL, ràng buộc subtype phụ thuộc discriminator, migration thêm cột làm thay đổi bảng chung.

### 13.2. Khi JOINED thường phù hợp

- Mỗi subtype có nhiều thuộc tính riêng bắt buộc và constraint quan trọng.
- Cần root entity được tham chiếu bởi FK và có uniqueness toàn hệ.
- Dữ liệu lớp cha và lớp con có thể được tối ưu/truy vấn riêng.
- Số subtype vừa phải, hoặc use case tải đầy đủ một subtype chiếm phần lớn.
- Chấp nhận JOIN và nhiều INSERT hơn để lấy schema chuẩn hóa.

**Điểm cần đánh đổi:** truy vấn đa hình có thể LEFT JOIN nhiều bảng; đường kế thừa sâu tăng số JOIN; ghi entity con liên quan nhiều bảng.

### 13.3. Khi TABLE_PER_CLASS thường phù hợp

- Các subtype gần như độc lập và phần lớn truy vấn chỉ theo từng loại cụ thể.
- Cần schema riêng và constraint rõ cho từng subtype.
- Truy vấn đa hình rất ít hoặc có thể giải quyết bằng một lớp báo cáo riêng.
- Chấp nhận duplicated columns/index và giải quyết global key ở kiến trúc khác.
- Không có nhiều FK bắt buộc phải tham chiếu trực tiếp một root table chung.

**Điểm cần đánh đổi:** UNION trong truy vấn đa hình, global uniqueness khó hơn, quan hệ tới root phức tạp hơn, cần generator ID hợp lệ toàn hierarchy.

### 13.4. Khi @MappedSuperclass thường phù hợp

- Mục tiêu chính là **dùng lại field và mapping**, không phải đa hình trong persistence.
- Mỗi subclass là một entity tương đối độc lập.
- Ứng dụng không cần JPQL query root chung hoặc association trỏ tới lớp cha như entity.
- Không cần database đảm bảo chung một unique key cho toàn bộ các bảng.

**Điểm cần đánh đổi:** không có entity root; nếu phát sinh yêu cầu “quản lý mọi loại Asset như một entity” về sau, có thể phải thiết kế lại schema và code.

## 14. Chi phí schema migration khi hệ phân cấp thay đổi

Một chiến lược có vẻ nhanh cho query hiện tại nhưng tốn công khi thêm subtype mới có thể không phù hợp nếu domain thường xuyên phát triển.

### 14.1. Thêm subtype mới

Giả sử thêm **Furniture** với thuộc tính **material** bắt buộc.

**SINGLE_TABLE:** thêm cột material vào assets; vì Laptop và Vehicle không có material, cột có thể phải nullable vật lý. Nếu DB dùng CHECK theo asset_type, phải cập nhật CHECK để chấp nhận FURNITURE và yêu cầu material đúng cho loại mới.

**JOINED:** thêm bảng furniture_assets với PK/FK tới assets và material NOT NULL; mapping root vẫn dùng chung. Query đa hình có thể sinh thêm JOIN.

**TABLE_PER_CLASS:** thêm bảng furniture_assets chứa cả id, assetCode, displayName và material; mở rộng query UNION, quy tắc global ID và uniqueness cần xem xét.

**@MappedSuperclass:** thêm Furniture như một entity độc lập thừa hưởng mapping; không có query root chung trừ khi ứng dụng tự tạo.

### 14.2. Thêm thuộc tính chung ở lớp cha

Giả sử thêm **purchaseDate** bắt buộc cho mọi Asset:

- SINGLE_TABLE: thêm một cột vào assets, xử lý backfill và NOT NULL trên một bảng.
- JOINED: thêm một cột vào assets, tương tự.
- TABLE_PER_CLASS: thêm purchase_date vào **mọi bảng concrete** và backfill từng bảng.
- @MappedSuperclass: tương tự, mỗi bảng entity kế thừa mapping phải thay.

Với hàng triệu dữ liệu cũ, thêm NOT NULL thường cần kế hoạch backfill, default và kiểm soát khóa bảng. Không nên chỉ đặt **@Column(nullable=false)** rồi giả định mọi DB sẽ migrate cột đang tồn tại đúng cách.

### 14.3. Di chuyển từ chiến lược này sang chiến lược khác

Đổi @Inheritance trên class rồi khởi động ứng dụng **không phải migration dữ liệu tự động an toàn**:

- SINGLE_TABLE → JOINED cần tách các cột/hàng subtype sang bảng con, duy trì ID và quan hệ.
- JOINED → SINGLE_TABLE cần hợp nhất các thuộc tính subtype vào bảng chung và xử lý CHECK/NULL.
- JOINED → TABLE_PER_CLASS cần nhân dữ liệu chung vào mỗi bảng concrete và xét mọi FK tới root.
- TABLE_PER_CLASS → JOINED cần tạo root table với ID duy nhất, gộp dữ liệu chung, sửa quan hệ và đảm bảo uniqueness toàn hệ.

Quá trình có thể ảnh hưởng tới stored procedures, views, index, audit, CDC và API. Nên dùng migration có phiên bản, kiểm tra dữ liệu cũ và có kế hoạch chuyển đổi khi nhiều phiên bản ứng dụng cùng chạy.

## 15. Những sai lầm thường gặp khi đánh giá chi phí

### 15.1. Chọn SINGLE_TABLE rồi đặt NOT NULL trên mọi field subtype

Nếu serialNumber chỉ có ý nghĩa với Laptop, một NOT NULL vật lý trên serial_number của bảng chung sẽ chặn cả Vehicle, vốn không có giá trị đó. Cần phân biệt nullable theo loại với nullable của một cột trên **mọi hàng trong bảng**; dùng CHECK theo discriminator hoặc chiến lược bảng riêng khi ràng buộc subtype là yêu cầu bắt buộc.

### 15.2. Cho rằng @Column(nullable=false) tự bảo đảm dữ liệu hợp lệ

Annotation thể hiện ý định mapping/schema generation nhưng không tự thay đổi một database đã triển khai trong mọi môi trường. Nếu sử dụng migration độc lập, cần đối chiếu DDL thực tế. Bean Validation và ràng buộc DB cũng phải được thiết kế cho phạm vi riêng; một validator Java không thay thế NOT NULL/UNIQUE/CHECK khi có nhiều nguồn ghi.

### 15.3. Cho rằng JOINED luôn tạo đúng một JOIN

Một hệ hai tầng có thể chỉ cần một JOIN để đọc một subtype, nhưng query đa hình đầy đủ có thể cần LEFT JOIN nhiều bảng subtype. Một cây kế thừa sâu cũng làm tăng số bảng cần đọc. Mặt khác, projection thuộc tính chung có thể tránh phần lớn JOIN subtype. Phải kiểm tra **SQL được sinh cho từng use case**.

### 15.4. Cho rằng TABLE_PER_CLASS không cần JOIN nên luôn nhanh

TABLE_PER_CLASS tránh JOIN thừa kế khi đọc **một subtype cụ thể** nhưng query **Asset** có thể đòi UNION nhiều bảng rồi ORDER BY/LIMIT. Số nhánh UNION và số hàng đầu vào có thể lớn. Nó còn làm quan hệ polymorphic và uniqueness toàn hệ phức tạp hơn.

### 15.5. Dùng UNIQUE trong từng bảng để bảo vệ business key toàn hệ

UNIQUE(asset_code) trên laptop_assets và vehicle_assets chỉ bảo vệ từng bảng. Hai bảng vẫn có thể cùng chứa mã ASSET-100. Nếu quy tắc nghiệp vụ yêu cầu duy nhất toàn hierarchy, cần root table, một bảng registry hoặc giải pháp đảm bảo uniqueness liên bảng khác.

### 15.6. Giả định khóa ngoại có thể tham chiếu một UNION view

Không có root table trong TABLE_PER_CLASS thì một FK SQL đơn giản không thể tự chọn Laptop hoặc Vehicle theo type. Một view kết hợp nhiều bảng không mặc nhiên là đích hợp lệ cho FOREIGN KEY trên mọi DB. Nếu cần tham chiếu Asset đa hình có ràng buộc DB mạnh, nên cân nhắc chiến lược có root table.

### 15.7. Đọc số JOIN mà không xem index và cardinality

Một JOIN qua PRIMARY KEY rất chọn lọc có thể rẻ. Một sequential scan một bảng rất lớn có thể đắt. Cần xem execution plan, số hàng thực, I/O và sorting thay vì kết luận từ số từ khóa JOIN.

### 15.8. Truy vấn entity đầy đủ khi chỉ cần DTO tóm tắt

Một màn hình chỉ cần id, mã và tên tài sản nhưng dùng **select a from Asset a** có thể khiến ORM materialize subtype, tải các cột không cần và giữ managed entity trong persistence context. DTO projection thường giảm dữ liệu, nhất là với JOINED hoặc TABLE_PER_CLASS.

### 15.9. Nhầm N+1 với chi phí JOINED

Nếu ứng dụng tải Asset rồi truy cập owner, tags hoặc maintenance records trong vòng lặp, ORM có thể tạo N+1 truy vấn do association/fetch plan. SINGLE_TABLE cũng có thể gặp N+1. Cần phân loại các SQL từ inheritance và SQL từ quan hệ nghiệp vụ.

### 15.10. Chạy benchmark bằng H2 rồi kết luận cho production DB

H2 có optimizer, DDL và dialect khác PostgreSQL, MySQL, Oracle hoặc SQL Server. Một bài test pass trên H2 chỉ chứng minh mapping hoạt động với H2 ở điều kiện đó. Khi chọn strategy vì hiệu năng hoặc constraint, cần đo trên DBMS/dialect/version tương đương môi trường triển khai.

### 15.11. Đổi chiến lược bằng một annotation mà không chuyển schema

Chuyển từ SINGLE_TABLE sang JOINED không tự sao chép dữ liệu các trường Laptop từ assets sang laptop_assets. Tương tự, TABLE_PER_CLASS cần bảng concrete chứa các cột chung và ID đúng. Cần migration và kế hoạch rollout rõ ràng.

### 15.12. Quên việc SQL UPDATE/INSERT khác nhau giữa các chiến lược

Đếm số SELECT chỉ phản ánh một phần workload. Với JOINED, INSERT subtype có thể chạm nhiều bảng; với TABLE_PER_CLASS, các cột chung lặp trong nhiều bảng; với SINGLE_TABLE, một bảng lớn mang cả index cho nhiều subtype. Nếu ứng dụng ghi nhiều, cần đo write throughput, lock và chi phí index bên cạnh tốc độ đọc.

### 15.13. Dùng TABLE_PER_CLASS với ID sinh độc lập ở mỗi bảng

Nếu mỗi subtype cấp ID riêng bắt đầu từ 1, Laptop #1 và Vehicle #1 có thể cùng tồn tại. Khi truy vấn và tham chiếu đa hình, cần đảm bảo danh tính duy nhất theo thiết kế của provider và ứng dụng. Shared sequence/UUID được tạo theo quy tắc rõ ràng thường đơn giản hơn nhiều cơ chế IDENTITY độc lập cho mỗi subtype.

### 15.14. Lạm dụng inheritance dù domain chỉ cần trường chung

Hai entity có vài thuộc tính giống nhau chưa chắc tạo thành một quan hệ **is-a** cần query đa hình. Nếu Laptop và Vehicle được vận hành hoàn toàn riêng, @MappedSuperclass hoặc composition có thể đủ. Dùng hệ phân cấp entity chỉ để tiết kiệm vài dòng Java có thể mang theo chi phí JOIN/UNION không cần thiết.

## 16. Bài tập đánh giá mô hình

### Bài 1: Ràng buộc bắt buộc của subtype

Mô hình SINGLE_TABLE có hai loại:

~~~text
asset_type = 'LAPTOP': serial_number bắt buộc
asset_type = 'VEHICLE': vin bắt buộc
~~~

**Câu hỏi:** Có nên khai báo cả serial_number và vin là NOT NULL vật lý trong bảng assets?

**Gợi ý:** Không. Mỗi hàng thuộc một subtype và không có giá trị cho thuộc tính subtype kia. Giữ cột nullable ở schema, cân nhắc CHECK theo discriminator và validation, hoặc dùng JOINED để NOT NULL nằm ở bảng riêng của subtype.

### Bài 2: Tính uniqueness toàn hierarchy

Ứng dụng dùng TABLE_PER_CLASS, mỗi bảng laptop_assets và vehicle_assets có UNIQUE(asset_code). Cả hai đều muốn lưu asset_code = "ASSET-007".

**Câu hỏi:** DB có tự cấm không?

**Gợi ý:** Không. UNIQUE theo từng bảng không có phạm vi liên bảng. Nếu cần uniqueness toàn hệ, cân nhắc bảng registry chứa assetCode duy nhất, một root table hoặc đổi chiến lược.

### Bài 3: Đếm số JOIN inheritance

Một query tải Laptop có Asset → Laptop trong JOINED. Một query khác tải mọi Asset với Laptop, Vehicle, Furniture, Drone.

**Câu hỏi:** Hai query có chắc cùng số JOIN không?

**Gợi ý:** Không. Query Laptop đầy đủ thường cần nối bảng cha và bảng Laptop; query đa hình có thể cần nhiều LEFT JOIN để phân biệt/tải các subtype. Số JOIN thật phụ thuộc SQL provider sinh và các cột cần lấy.

### Bài 4: Chọn strategy cho hệ ghi nhiều và ít truy vấn đa hình

Một hệ nhập kho có bốn loại tài sản. Mỗi loại có 20 trường riêng và các trường đó có nhiều constraint NOT NULL. 98% truy vấn chỉ đọc từng subtype, hiếm có API hỏi tất cả Asset.

**Câu hỏi:** Chiến lược nào đáng cân nhắc?

**Gợi ý:** JOINED và TABLE_PER_CLASS đều đáng xem vì cột subtype ở bảng riêng; TABLE_PER_CLASS có thể tránh JOIN cho query subtype nhưng gây khó nếu cần FK/unique toàn hệ. @MappedSuperclass phù hợp nếu không cần entity root đa hình. Cần xem quan hệ tới Asset, schema và workload thật thay vì chọn chỉ theo con số 98%.

### Bài 5: Chọn strategy cho API đa hình tần suất cao

Một ứng dụng hiển thị danh sách toàn bộ Asset, lọc theo assetCode và có nhiều MaintenanceRecord tham chiếu tới Asset bất kể loại. Mỗi subtype chỉ có hai trường riêng.

**Câu hỏi:** Phương án nào có lợi thế?

**Gợi ý:** SINGLE_TABLE là ứng viên mạnh vì một bảng và một FK root, truy vấn đa hình đơn giản, global UNIQUE(assetCode) trực tiếp. JOINED vẫn phù hợp nếu constraint subtype quan trọng; cần so sánh SQL thực tế.

### Bài 6: Đọc execution plan

Query JOINED từ assets tới laptop_assets có một JOIN nhưng trả 20 hàng trong vài mili giây nhờ index PK. Query SINGLE_TABLE không JOIN nhưng quét toàn bộ hàng triệu assets.

**Câu hỏi:** Có thể kết luận SINGLE_TABLE luôn nhanh hơn vì ít JOIN hơn không?

**Gợi ý:** Không. Phải xét WHERE, selectivity, index và số page đã đọc. Một JOIN nhỏ qua index có thể rất rẻ; số JOIN chỉ là một biến trong chi phí.

### Bài 7: Migration thêm một subtype

Hệ có SINGLE_TABLE và CHECK yêu cầu trường theo asset_type. Team thêm Furniture với material bắt buộc.

**Câu hỏi:** Ngoài tạo class Java cần thay đổi gì?

**Gợi ý:** Thêm cột material, cập nhật CHECK cho discriminator FURNITURE, xem index và dữ liệu chuyển đổi. Nếu JOINED, chủ yếu thêm bảng Furniture có FK tới root và constraint riêng, nhưng query đa hình có thể thêm nhánh join.

### Bài 8: Phân trang đa hình

Một query Asset ORDER BY assetCode OFFSET 100000 LIMIT 20 chạy trên TABLE_PER_CLASS với mười bảng concrete lớn.

**Câu hỏi:** Vì sao có thể tốn nhiều tài nguyên?

**Gợi ý:** Provider có thể UNION các nhánh rồi sắp xếp/loại bỏ nhiều hàng để tìm trang sâu. Cần quan sát SQL và plan, cân nhắc projection, index phù hợp và keyset pagination với khóa sắp xếp ổn định.

### Bài 9: N+1 không phải do inheritance

Một query Asset SINGLE_TABLE trả 100 hàng, sau đó service gọi getOwner().getName() cho mỗi Asset và thấy thêm 100 câu SELECT.

**Câu hỏi:** Chuyển sang JOINED có tự giải quyết không?

**Gợi ý:** Không. N+1 phát sinh từ association và fetch plan. Cần truy vấn/fetch owner phù hợp với nhu cầu, DTO projection hoặc entity graph, không kỳ vọng inheritance strategy sửa lỗi.

### Bài 10: Đánh giá DDL và ứng dụng

Team đánh dấu @Column(nullable=false) trên Laptop.serialNumber trong SINGLE_TABLE, nhưng DDL production cho phép NULL và đã có một hàng Laptop bị thiếu serial.

**Câu hỏi:** Vì sao annotation chưa đủ?

**Gợi ý:** Mapping Java không đảm bảo constraint vật lý tự có trên schema đã tồn tại. Hơn nữa, NOT NULL toàn cột sẽ ảnh hưởng Vehicle. Cần ràng buộc theo discriminator hoặc chuyển schema, migration dữ liệu cũ và validation ứng dụng.

## 17. Checklist khi đánh giá một chiến lược kế thừa

Trước khi chốt @Inheritance, nên có câu trả lời cho những điểm sau:

1. **Có thật sự cần polymorphic entity query không?** Nếu không, @MappedSuperclass hoặc composition có thể phù hợp.
2. **Có bao nhiêu subtype và bao nhiêu cấp sâu?** Cây rộng ảnh hưởng JOIN/UNION, cây sâu ảnh hưởng JOINED theo tầng.
3. **Bao nhiêu cột chỉ có ý nghĩa với một subtype?** SINGLE_TABLE có thể cần nhiều cột nullable và CHECK.
4. **Có những NOT NULL/UNIQUE/CHECK quan trọng nào?** Chúng áp dụng toàn hệ hay chỉ một subtype?
5. **Có cần assetCode duy nhất toàn hệ không?** Root table giúp dễ tạo UNIQUE xuyên hierarchy.
6. **Có nhiều FK tới lớp cha không?** SINGLE_TABLE/JOINED có bảng root thuận lợi.
7. **Workload nào chiếm đa số?** Chi tiết subtype, danh sách đa hình, thống kê hay cập nhật dữ liệu?
8. **Query có cần dựng entity đầy đủ không?** Projection có thể tránh join/tải cột không cần.
9. **Có phân trang đa hình hoặc ORDER BY lớn không?** TABLE_PER_CLASS có thể phải hợp nhất nhiều bảng.
10. **Provider sinh SQL thế nào?** Dựa vào log/EXPLAIN thật, không chỉ đọc annotation.
11. **Các JOIN có phải do inheritance hay do association?** Phân biệt với N+1 để tối ưu đúng chỗ.
12. **Chi phí ghi và migration chấp nhận được không?** Cần xem số INSERT, index, DDL thêm subtype và dữ liệu cũ.
13. **Tài khoản DB và schema hiện tại hỗ trợ constraint nào?** CHECK, partial index và DDL phụ thuộc DBMS.
14. **Đã có benchmark đại diện chưa?** Thử đúng DBMS/provider/dialect và tỉ lệ subtype thực tế.

## 18. Tổng kết

Trong kế thừa JPA, **ràng buộc cột, số phép nối và chi phí truy vấn là ba mặt của cùng một quyết định ánh xạ**:

- **SINGLE_TABLE** giữ mọi entity trong một bảng: query đa hình và khóa ngoại tới root tương đối đơn giản, không cần JOIN inheritance; đổi lại cột riêng subtype thường phải nullable và ràng buộc bắt buộc theo subtype cần CHECK/validation phù hợp.
- **JOINED** chia cột theo bảng cha–con: NOT NULL/UNIQUE/CHECK riêng subtype dễ biểu diễn hơn và root vẫn được tham chiếu bằng FK; đổi lại đọc đầy đủ subtype thường cần JOIN và ghi entity con liên quan nhiều bảng.
- **TABLE_PER_CLASS** chứa đủ cột ở từng bảng concrete: đọc riêng subtype có thể không cần JOIN, nhưng query đa hình có thể dùng UNION, uniqueness xuyên hierarchy và FK tới root khó hơn.
- **@MappedSuperclass** chỉ dùng lại mapping: đơn giản khi các entity độc lập, nhưng không có root entity để truy vấn đa hình.

Đừng lựa chọn chỉ bằng cách đếm JOIN trong một câu SQL minh họa. Hãy bắt đầu từ **ràng buộc dữ liệu phải được DB bảo vệ**, **những truy vấn thực sự quan trọng**, **số subtype và chiều sâu hierarchy**, rồi quan sát **SQL mà provider sinh và execution plan trên DB thực tế**. Một chiến lược tốt là chiến lược đáp ứng đúng ngữ nghĩa dữ liệu với tổng chi phí đọc, ghi và thay đổi schema chấp nhận được trong vòng đời ứng dụng.
