# Ánh xạ cột khóa Map và khóa Map là entity trong JPA

Trong Jakarta Persistence (JPA), một thuộc tính kiểu `Map<K, V>` có thể mô tả tập hợp các phần tử được truy cập bằng **khóa**. Khác `List` thường truy cập theo vị trí và `Set` kiểm tra tư cách thành viên, `Map` biểu diễn quan hệ **mỗi khóa liên kết với tối đa một giá trị** trong phạm vi một collection tại thời điểm nhất định.

Ví dụ:

- Tài khoản có các thiết lập `Map<String, String>`: khóa `"theme"`, `"locale"`; giá trị `"dark"`, `"vi-VN"`.
- Danh mục sản phẩm có mức giá theo loại tiền `Map<Currency, BigDecimal>`.
- Kế hoạch giá có quy tắc ứng với từng vùng `Map<Region, PricingRule>`, trong đó **Region là một entity**.
- Nhóm làm việc có `Map<String, Employee>`, lấy chức danh làm khóa để tìm nhân viên phụ trách.

JPA cần giải quyết hai câu hỏi tách biệt:

1. **Khóa Map được lưu và ánh xạ ở đâu?** Nó là cột basic, foreign key tới một entity, hay là thuộc tính đã có của entity giá trị?
2. **Giá trị Map thuộc loại nào?** Nó là basic/embeddable value của `@ElementCollection`, hay một entity được liên kết qua `@OneToMany`/`@ManyToMany`?

Từ hai câu hỏi đó, các annotation có vai trò khác nhau:

- `@MapKeyColumn`: ánh xạ **cột khóa** khi khóa là giá trị basic được lưu như một cột trong collection/join table.
- `@MapKeyJoinColumn`: ánh xạ **khóa ngoại của khóa Map là entity**.
- `@MapKey`: chỉ định **một thuộc tính của entity giá trị** làm khóa; có thể lấy ID hoặc thuộc tính khác của entity đó.
- `@MapKeyEnumerated`, `@MapKeyTemporal`, `@Convert`: xử lý một số loại khóa basic và representation của chúng theo quy tắc JPA.
- `@CollectionTable` hoặc `@JoinTable`: chọn bảng chứa collection/liên kết khi mô hình cần bảng riêng.

Bài học thuộc chương **Tập hợp và Map** trong module *Data Persistence Relational Access ORM JPA*, tập trung vào cách đọc mô hình quan hệ đằng sau các annotation, những khác biệt giữa khóa basic và khóa entity, và cách duy trì tính nhất quán khi cập nhật Map.

## 1. Ngữ nghĩa của Map khác danh sách và tập hợp

Ở Java:

```java
Map<String, String> settings = new HashMap<>();

settings.put("theme", "dark");
settings.put("locale", "vi-VN");

String theme = settings.get("theme"); // "dark"
settings.put("theme", "light");        // Thay giá trị cho cùng khóa.
settings.remove("locale");             // Bỏ một mục.
```

Các tính chất đáng chú ý:

| Kiểu tập hợp | Cách định danh phần tử | Điều đặc biệt |
|---|---|---|
| `List<E>` | Vị trí/phần tử | Có thể có phần tử trùng; có thể cần cột thứ tự nếu muốn lưu vị trí |
| `Set<E>` | Equality của phần tử | Phần tử duy nhất theo `equals/hashCode` |
| `Map<K, V>` | Equality của khóa `K` | Mỗi khóa ánh xạ tối đa một giá trị `V` |

Giả sử hai đối tượng `Region` biểu diễn cùng một hàng trong database nhưng Java `equals/hashCode` xem chúng khác nhau: `HashMap` có thể chứa hai key mà về nghiệp vụ cùng một vùng. Vì vậy, với **entity làm key**, tính ổn định của equality là một phần quan trọng của thiết kế, không chỉ annotation JPA.

Cũng cần phân biệt hai mức duy nhất:

- **Trong Java:** `Map` ngăn khóa trùng theo `equals/hashCode`.
- **Trong database:** muốn ngăn hai hàng collection trùng cùng một khóa của cùng chủ sở hữu, phải có **ràng buộc duy nhất** hoặc khóa chính phù hợp.

`Map` không thay thế database constraint, nhất là khi có nhiều transaction cập nhật đồng thời.

## 2. Bức tranh tổng quát của Map persistent

Một Map persistent không nhất thiết được lưu bằng một bảng “Map” độc lập do JPA tự tạo. Tùy mapping, dữ liệu có thể nằm ở:

- **Collection table**: phổ biến với `@ElementCollection Map<BasicKey, BasicValue>`.
- **Join table**: phổ biến khi Map biểu diễn liên kết entity qua bảng nối; cả key và value có thể có FK riêng.
- **Bảng của entity giá trị**: khi Map dùng thuộc tính đã persistent trong entity giá trị làm khóa qua `@MapKey`.
- **Bảng của phía chứa FK**: trong một số mapping `@OneToMany`/quan hệ thích hợp; vị trí cột phụ thuộc việc quan hệ là một hay hai chiều và cấu hình ownership.

Sơ đồ khái niệm:

```text
                        Map<K, V> trong entity
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
       K là basic          K là entity         K lấy từ
       value               độc lập              property của V
             |                  |                  |
             v                  v                  v
      @MapKeyColumn        @MapKeyJoinColumn      @MapKey
             |                  |                  |
             v                  v                  v
       Cột khóa basic       Cột FK trỏ entity      Dùng cột đã ánh xạ
       trong table          làm khóa               ở entity value
             |                  |                  |
             +------------------+------------------+
                                |
                   Cách V được ánh xạ cũng quan trọng:
                   @ElementCollection / @OneToMany /
                   @ManyToMany
```

Không nên quyết định annotation chỉ bằng việc thấy `Map`. Cần xác định **kiểu K**, **kiểu V** và **mối quan hệ giữa chủ Map với V**.

## 3. Map có khóa basic: `@MapKeyColumn`

### 3.1. Ví dụ thiết lập tài khoản

Giả sử một tài khoản có các thiết lập dưới dạng chuỗi:

```java
private Map<String, String> preferences;
```

Mỗi tài khoản có thể có:

```text
account_id = 7
  "theme"    -> "dark"
  "language" -> "vi"
  "timezone" -> "Asia/Ho_Chi_Minh"
```

Một schema phù hợp:

```sql
CREATE TABLE app_account (
    id BIGINT PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

CREATE TABLE account_preference (
    account_id BIGINT NOT NULL,
    preference_key VARCHAR(80) NOT NULL,
    preference_value VARCHAR(500),

    CONSTRAINT pk_account_preference
        PRIMARY KEY (account_id, preference_key),

    CONSTRAINT fk_preference_account
        FOREIGN KEY (account_id) REFERENCES app_account(id)
);
```

Trong `account_preference`, `preference_key` **không tham chiếu tới entity nào**. Nó chỉ là chuỗi được dùng làm khóa trong Map.

### 3.2. Mapping JPA đầy đủ

```java
package com.example.persistence;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

@Entity
@Table(name = "app_account")
public class AppAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String username;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "account_preference",
        joinColumns = @JoinColumn(name = "account_id"),
        uniqueConstraints = @UniqueConstraint(
            columnNames = {"account_id", "preference_key"}
        )
    )
    @MapKeyColumn(
        name = "preference_key",
        nullable = false,
        length = 80
    )
    @Column(name = "preference_value", length = 500)
    private Map<String, String> preferences = new HashMap<>();

    protected AppAccount() {
    }

    public AppAccount(String username) {
        this.username = Objects.requireNonNull(username);
    }

    public Long getId() {
        return id;
    }

    public Map<String, String> getPreferences() {
        return Collections.unmodifiableMap(preferences);
    }

    public void changePreference(String key, String value) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Thiếu khóa thiết lập");
        }
        if (value == null) {
            throw new IllegalArgumentException("Giá trị không được null");
        }
        preferences.put(key, value);
    }

    public void removePreference(String key) {
        preferences.remove(key);
    }
}
```

Chú ý các vai trò:

1. `@ElementCollection`: các phần tử trong Map là **value/basic data**, không phải entity có vòng đời riêng.
2. `@CollectionTable`: khai báo bảng `account_preference`.
3. `@JoinColumn(name = "account_id")`: cột liên kết collection row với chủ sở hữu `AppAccount`.
4. `@MapKeyColumn(name = "preference_key")`: cột lưu **khóa String** của Map.
5. `@Column(name = "preference_value")`: cột lưu **giá trị String** của Map.
6. `@UniqueConstraint`: khẳng định một tài khoản không có hai row cho cùng khóa.
7. Phương thức `changePreference` không thay thế cả Map, mà thay đổi collection đang được JPA quản lý.

Trong ví dụ này, `@MapKeyColumn` **không tạo khóa ngoại**. Nó chỉ mô tả kiểu cột của **khóa Map dạng basic**.

### 3.3. Đọc một bản ghi dưới góc nhìn Java và SQL

Bảng:

| account_id | preference_key | preference_value |
|---:|---|---|
| 7 | theme | dark |
| 7 | language | vi |
| 7 | timezone | Asia/Ho_Chi_Minh |

Tương ứng:

```java
account.getPreferences().get("theme");    // "dark"
account.getPreferences().get("language"); // "vi"
```

Khi thay:

```java
account.changePreference("theme", "light");
```

Provider có thể cập nhật row phù hợp với khóa `(account_id = 7, preference_key = "theme")`, hoặc phát SQL theo chiến lược collection tracking của nó. JPA không cam kết từng lệnh `Map.put` sẽ luôn tương ứng đúng một `UPDATE`; ORM có thể dùng DELETE/INSERT, batch hoặc các cách đồng bộ khác.

Khi xóa:

```java
account.removePreference("language");
```

về mặt trạng thái bền vững, row có khóa `language` của account đó sẽ không còn sau khi transaction hoàn tất thành công.

### 3.4. `@MapKeyColumn` và `@Column` khác nhau

Đây là một trong những chỗ dễ nhầm nhất:

```java
@MapKeyColumn(name = "preference_key") // Cột K.
@Column(name = "preference_value")      // Cột V.
private Map<String, String> preferences;
```

| Annotation | Ánh xạ | Với `Map<String, String>` |
|---|---|---|
| `@MapKeyColumn` | Khóa `K` | `"theme"` |
| `@Column` | Giá trị `V` | `"dark"` |
| `@CollectionTable` | Bảng chứa cặp key–value | `account_preference` |
| `@JoinColumn` bên trong `@CollectionTable` | FK tới entity chủ Map | `account_id` |

Nếu đổi `@Column(name = "preference_value")` thành `@Column(name = "preference_key")`, điều đó **không có nghĩa** đã đổi khóa Map; bạn đang cấu hình nhầm **cột giá trị** trùng tên với cột khóa.

## 4. Cấu hình kiểu khóa basic: enum, thời gian và converter

### 4.1. Enum làm Map key

Giả sử hệ thống lưu tỷ lệ quy đổi theo mã tiền tệ:

```java
public enum CurrencyCode {
    VND,
    USD,
    EUR
}
```

Entity:

```java
@Entity
@Table(name = "exchange_rate_book")
public class ExchangeRateBook {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "exchange_rate",
        joinColumns = @JoinColumn(name = "book_id")
    )
    @MapKeyEnumerated(EnumType.STRING)
    @MapKeyColumn(name = "currency_code", length = 3)
    @Column(name = "rate", precision = 18, scale = 6)
    private Map<CurrencyCode, BigDecimal> rates = new HashMap<>();

    protected ExchangeRateBook() {
    }
}
```

Bảng:

```text
exchange_rate
+---------+---------------+------------+
| book_id | currency_code | rate       |
+---------+---------------+------------+
| 1       | VND           | 1.000000   |
| 1       | USD           | 26000.0000 |
| 1       | EUR           | 28000.0000 |
+---------+---------------+------------+
```

`@MapKeyEnumerated(EnumType.STRING)` dành cho **enum ở vị trí khóa của Map**. Nó khác `@Enumerated` thường dùng cho một thuộc tính enum đơn lẻ.

Vì `EnumType.STRING` lưu tên enum, đổi tên constant sau khi có dữ liệu cần migration thích hợp. Nếu dùng ordinal, chèn/sắp xếp enum constants có thể khiến ý nghĩa dữ liệu cũ bị thay đổi; lựa chọn STRING thường rõ ràng hơn khi có thể.

### 4.2. Khóa thời gian

Với Map có key kiểu ngày thời gian, annotation chuyên biệt có thể là `@MapKeyTemporal` cho các kiểu thời gian legacy được hỗ trợ:

```java
@ElementCollection
@CollectionTable(
    name = "daily_measurement",
    joinColumns = @JoinColumn(name = "device_id")
)
@MapKeyTemporal(TemporalType.DATE)
@MapKeyColumn(name = "measurement_day")
@Column(name = "value")
private Map<java.util.Date, Double> measurements;
```

Cần cân nhắc:

- `@MapKeyTemporal` được dùng trong ngữ cảnh temporal key truyền thống; không tự áp đặt nó lên mọi kiểu `java.time`.
- `java.time.LocalDate` thường có mapping basic trong các phiên bản JPA hiện đại; hãy chọn đúng kiểu theo ngữ nghĩa.
- Nếu key là `java.util.Date` mutable và bị sửa sau khi đưa vào `HashMap`, hash/equality có thể thay đổi, khiến collection không hoạt động như dự kiến.
- Trên entity managed, thay đổi key có thể khiến ORM phải xóa liên kết cũ và tạo liên kết mới; không nên “sửa tại chỗ” một key mutable.

### 4.3. Value object làm khóa với `AttributeConverter`

Một khóa basic không bắt buộc phải là `String` hoặc enum. Bạn có thể tạo value object `FeatureCode`:

```java
public record FeatureCode(String value) {

    public FeatureCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Feature code rỗng");
        }
    }
}
```

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class FeatureCodeConverter
        implements AttributeConverter<FeatureCode, String> {

    @Override
    public String convertToDatabaseColumn(FeatureCode key) {
        return key == null ? null : key.value();
    }

    @Override
    public FeatureCode convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new FeatureCode(dbValue);
    }
}
```

Map mapping:

```java
@ElementCollection
@CollectionTable(
    name = "account_feature",
    joinColumns = @JoinColumn(name = "account_id")
)
@MapKeyColumn(name = "feature_code", length = 80)
@Convert(
    attributeName = "key",
    converter = FeatureCodeConverter.class
)
@Column(name = "enabled")
private Map<FeatureCode, Boolean> enabledFeatures = new HashMap<>();
```

Ở đây:

- `@MapKeyColumn` xác định **cột** chứa key.
- `@Convert(attributeName = "key", ...)` chuyển **kiểu Java của key** sang representation phù hợp.
- `@Column(name = "enabled")` xác định cột value là Boolean.
- Nếu muốn cấu hình converter cho **Map value**, quy tắc `@Convert` có cú pháp `attributeName = "value"` tương ứng đối với basic value.

Cách này khác hoàn toàn `@MapKeyJoinColumn`: `FeatureCode` là **value object/basic key**, không phải entity được khóa ngoại tham chiếu.

**Giới hạn:** Converter phải phù hợp kiểu basic mà provider/JDBC có thể lưu. Nó không tự tạo một quan hệ entity hoặc foreign key chỉ vì key có tên “Code”.

## 5. Khóa Map là entity: `@MapKeyJoinColumn`

### 5.1. Bản chất của entity key

Bây giờ giả sử một hệ thống định giá có:

- `PricingPlan`: một kế hoạch giá.
- `Region`: entity biểu diễn vùng áp dụng (Việt Nam, Đông Nam Á, châu Âu...).
- `PricingRule`: entity biểu diễn một quy tắc giá cụ thể.

Mỗi PricingPlan cần tìm **một PricingRule ứng với từng Region**:

```java
Map<Region, PricingRule> rulesByRegion;
```

Trong Map này:

- **`Region` là entity key**, có identity và bảng dữ liệu riêng.
- **`PricingRule` là entity value**, cũng có identity và bảng dữ liệu riêng.
- Một cặp map entry liên kết `PricingPlan`, `Region` và `PricingRule`.
- Khóa Map không phải chuỗi `"VN"` mà là reference đến một row `Region`.

Để ánh xạ entity key thành khóa ngoại, JPA có **`@MapKeyJoinColumn`**.

### 5.2. Sơ đồ quan hệ

Một cách lưu Map này dùng join table:

```text
pricing_plan              pricing_plan_rule              pricing_rule
+---------------+       +---------------------+        +-----------------+
| id (PK)       |<------| plan_id (FK)        |        | id (PK)         |
| name          |       | region_id (FK key)  |        | rule_name       |
+---------------+       | rule_id (FK value)  |------->| multiplier      |
                        +---------------------+        +-----------------+
                                  |
                                  | region_id
                                  v
                                region
                         +------------------+
                         | id (PK)          |
                         | code (UNIQUE)    |
                         | display_name     |
                         +------------------+
```

Khác `@ElementCollection Map<String, String>`, join table ở đây có **ba vai trò khóa**:

1. `plan_id`: tham chiếu entity **chủ Map**.
2. `region_id`: tham chiếu entity **khóa Map**.
3. `rule_id`: tham chiếu entity **giá trị Map**.

Đối với mỗi `plan_id`, `region_id` phải duy nhất nếu muốn mỗi vùng có tối đa một quy tắc trong kế hoạch đó.

### 5.3. Entity Region

```java
package com.example.pricing;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "region")
public class Region {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 20)
    private String code;

    @Column(name = "display_name", nullable = false, length = 100)
    private String displayName;

    protected Region() {
    }

    public Region(String code, String displayName) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Code vùng không hợp lệ");
        }
        this.code = code;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }
}
```

`Region` có một identity riêng là `id`. Đây không phải embeddable hay converter-mapped basic value. `code` là business key hữu ích cho giao diện, nhưng key Map ở mô hình sắp tới vẫn là **entity Region**, còn DB lưu reference qua `region_id`.

### 5.4. Entity PricingRule

```java
package com.example.pricing;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "pricing_rule")
public class PricingRule {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "rule_name", nullable = false, length = 100)
    private String ruleName;

    @Column(nullable = false, precision = 10, scale = 4)
    private BigDecimal multiplier;

    protected PricingRule() {
    }

    public PricingRule(String ruleName, BigDecimal multiplier) {
        if (ruleName == null || ruleName.isBlank()) {
            throw new IllegalArgumentException("Thiếu tên quy tắc");
        }
        if (multiplier == null || multiplier.signum() <= 0) {
            throw new IllegalArgumentException("Multiplier phải dương");
        }
        this.ruleName = ruleName;
        this.multiplier = multiplier;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getMultiplier() {
        return multiplier;
    }
}
```

Vì `PricingRule` là entity, JPA sẽ quản lý lifecycle của nó theo quan hệ entity và các thao tác persist/merge/remove phù hợp. Không xử lý nó như một chuỗi hoặc một object không định danh.

### 5.5. PricingPlan với khóa Map là Region entity

```java
package com.example.pricing;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.MapKeyJoinColumn;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

@Entity
@Table(name = "pricing_plan")
public class PricingPlan {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @OneToMany
    @JoinTable(
        name = "pricing_plan_rule",
        joinColumns = @JoinColumn(name = "plan_id"),
        inverseJoinColumns = @JoinColumn(name = "rule_id"),
        uniqueConstraints = {
            @UniqueConstraint(
                name = "uq_plan_region",
                columnNames = {"plan_id", "region_id"}
            ),
            @UniqueConstraint(
                name = "uq_plan_rule_value",
                columnNames = {"rule_id"}
            )
        }
    )
    @MapKeyJoinColumn(
        name = "region_id",
        referencedColumnName = "id",
        nullable = false
    )
    private Map<Region, PricingRule> rulesByRegion = new HashMap<>();

    protected PricingPlan() {
    }

    public PricingPlan(String name) {
        this.name = Objects.requireNonNull(name);
    }

    public Long getId() {
        return id;
    }

    public Map<Region, PricingRule> getRulesByRegion() {
        return Collections.unmodifiableMap(rulesByRegion);
    }

    public void assignRule(Region region, PricingRule rule) {
        Objects.requireNonNull(region, "region");
        Objects.requireNonNull(rule, "rule");

        rulesByRegion.put(region, rule);
    }

    public void removeRegion(Region region) {
        rulesByRegion.remove(region);
    }
}
```

Điểm cần hiểu sâu:

- `@OneToMany` ở đây khai báo **tập entity giá trị `PricingRule`** được tham chiếu bởi `PricingPlan`. Mapping này là một chiều, dùng join table rõ ràng.
- `@JoinTable` mô tả bảng nối giữa **chủ Map (PricingPlan)** và **entity value (PricingRule)**.
- `@MapKeyJoinColumn(name = "region_id")` mô tả **FK của entity key (Region)** trong chính bảng liên kết được dùng cho Map.
- `@MapKeyJoinColumn` **không thay thế** `@JoinTable`; hai annotation có vai trò khác nhau.
- `@UniqueConstraint(plan_id, region_id)` ngăn trùng key trong cùng một kế hoạch.
- `@UniqueConstraint(rule_id)` thể hiện lựa chọn mỗi rule entity thuộc một plan trong mô hình `@OneToMany` này. Nếu quy tắc cần được nhiều plan dùng chung, phải thiết kế lại ownership/multiplicity phù hợp (có thể chọn `@ManyToMany` với map value entity hoặc mô hình liên kết riêng).
- Không cấu hình cascade mặc định: code cần đảm bảo `Region` và `PricingRule` đã được persist hoặc có identity hợp lệ trước khi ghi quan hệ.

**Lưu ý:** Mọi constraint về business key, quyền sử dụng Region, và việc một PricingRule được dùng chung hay không vẫn là quyết định nghiệp vụ. Ví dụ chọn các ràng buộc nhất quán với một trường hợp cụ thể, không phải schema mặc định bắt buộc của mọi Map entity-key.

### 5.6. Schema tương ứng

```sql
CREATE TABLE region (
    id BIGINT PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL
);

CREATE TABLE pricing_rule (
    id BIGINT PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,
    multiplier DECIMAL(10, 4) NOT NULL
);

CREATE TABLE pricing_plan (
    id BIGINT PRIMARY KEY,
    name VARCHAR(255)
);

CREATE TABLE pricing_plan_rule (
    plan_id BIGINT NOT NULL,
    region_id BIGINT NOT NULL,
    rule_id BIGINT NOT NULL,

    CONSTRAINT uq_plan_region UNIQUE (plan_id, region_id),
    CONSTRAINT uq_plan_rule_value UNIQUE (rule_id),

    CONSTRAINT fk_ppr_plan
        FOREIGN KEY (plan_id) REFERENCES pricing_plan(id),
    CONSTRAINT fk_ppr_region
        FOREIGN KEY (region_id) REFERENCES region(id),
    CONSTRAINT fk_ppr_rule
        FOREIGN KEY (rule_id) REFERENCES pricing_rule(id)
);
```

Một hàng:

```text
plan_id = 5
region_id = 2   (Region "VN")
rule_id = 12    (PricingRule "VN_STANDARD")
```

thể hiện:

```java
plan.getRulesByRegion().get(regionVn); // PricingRule(id=12)
```

**Chính `region_id` là cột khóa Map**, còn `rule_id` là cột tham chiếu Map value. Cả hai đều là khóa ngoại tới entity; phân biệt vai trò chúng là cốt lõi của `@MapKeyJoinColumn`.

## 6. `@MapKeyColumn` khác `@MapKeyJoinColumn` ở đâu?

| Đặc điểm | `@MapKeyColumn` | `@MapKeyJoinColumn` |
|---|---|---|
| Kiểu Map key | Basic/value type có mapping cột | Entity được tham chiếu |
| Cột key trong DB | Giá trị dữ liệu trực tiếp | Khóa ngoại tới bảng entity key |
| Ví dụ K | `String`, `Integer`, enum, value object chuyển thành basic | `Region`, `Department`, `User` |
| Tính toàn vẹn tham chiếu | Không có FK chỉ vì dùng `@MapKeyColumn` | Có thể/cần FK tham chiếu entity key |
| Annotation liên quan | `@MapKeyEnumerated`, `@MapKeyTemporal`, `@Convert` | `@JoinColumn` cho các quan hệ khác; `@MapKeyJoinColumns` khi khóa ghép |
| Cách JPA nhận diện key | Equality của giá trị Java | Identity entity + equality thích hợp trong Map |
| Ví dụ SQL | `feature_code = 'X'` | `region_id = 12` trỏ `region.id` |
| Nếu cần đọc dữ liệu của key | Giá trị nằm ngay trong cột | Có thể phát sinh truy cập entity key tùy fetch strategy |
| Khi xóa entry | Xóa/cập nhật row collection | Xóa liên kết; **không mặc định xóa entity key** |

Một quy tắc thực hành: **Nếu key trong Java là một entity có `@Id` và bảng riêng, đừng dùng `@MapKeyColumn` như thể entity đó chỉ là chuỗi ID.** Hãy cân nhắc `@MapKeyJoinColumn` hoặc `@MapKey` nếu key thực chất là thuộc tính đã ánh xạ của value entity.

## 7. `@MapKey`: lấy khóa từ entity giá trị, không tạo cột khóa độc lập

Đây là trường hợp thường bị nhầm với hai annotation trên.

Giả sử mỗi `InventoryItem` là một entity, có `sku` và tham chiếu tới kho `Warehouse`:

```java
@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "warehouse_id", nullable = false)
    private Warehouse warehouse;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected InventoryItem() {
    }

    public String getSku() {
        return sku;
    }
}
```

Một kho muốn tìm item theo SKU:

```java
@Entity
@Table(name = "warehouse")
public class Warehouse {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "warehouse")
    @MapKey(name = "sku")
    private Map<String, InventoryItem> itemsBySku =
        new HashMap<>();

    protected Warehouse() {
    }
}
```

Ở đây:

- `Warehouse.itemsBySku` là collection các **entity value `InventoryItem`**.
- `@MapKey(name = "sku")` nói rằng key là **thuộc tính persistent `InventoryItem.sku`**.
- `mappedBy = "warehouse"` nói rằng `InventoryItem.warehouse` quản lý association một-nhiều.
- **Không cần thêm một cột map_key vào join table**. Key đã nằm ở `inventory_item.sku`.
- Schema tương ứng cần bảng `inventory_item` với `warehouse_id` và `sku`; thường nên có unique constraint `(warehouse_id, sku)` nếu muốn mỗi SKU chỉ có một item trong mỗi kho.

Sơ đồ:

```text
warehouse
+----------+
| id (PK)  |
+----------+
     ^
     |
     | inventory_item.warehouse_id
     |
inventory_item
+----------------+
| id (PK)        |
| warehouse_id   |
| sku            | <------- Map key qua @MapKey("sku")
| quantity       |
+----------------+
        |
        v
Warehouse.itemsBySku : Map<String, InventoryItem>
        "SKU-123" -> InventoryItem(id=88)
```

**Điểm khác biệt:** `@MapKeyColumn` và `@MapKeyJoinColumn` mô tả **cột khóa dành cho map mapping**; `@MapKey(name = "...")` dùng **thuộc tính sẵn có của entity value** làm key.

### 7.1. `@MapKey` rỗng nghĩa là gì?

Nếu dùng `@MapKey` mà không cung cấp `name`, theo quy tắc của association Map, key được lấy từ **primary key của entity value**. Ví dụ, nếu value là `InventoryItem` có ID `Long`, có thể ánh xạ Map keyed by ID:

```java
@OneToMany(mappedBy = "warehouse")
@MapKey
private Map<Long, InventoryItem> itemsById =
    new HashMap<>();
```

Ở đây key là `InventoryItem.id`, không phải một cột key độc lập. Tuy nhiên, cần thiết kế lưu ý trạng thái ID trước/sau persist: key chưa được sinh khi entity mới đang transient và việc chèn vào Map trước khi biết ID có thể không phù hợp.

### 7.2. Khi `@MapKey` tham chiếu thuộc tính association

Một entity value có thể chứa một reference tới entity khác:

```java
@Entity
public class RegionalPricingRule {

    @Id
    private Long id;

    @ManyToOne
    private PricingPlan plan;

    @ManyToOne
    @JoinColumn(name = "region_id")
    private Region region;

    private BigDecimal multiplier;

    protected RegionalPricingRule() {
    }
}
```

Một `PricingPlan` có thể được cấu hình:

```java
@OneToMany(mappedBy = "plan")
@MapKey(name = "region")
private Map<Region, RegionalPricingRule> rulesByRegion;
```

Ở ví dụ này, **Map key là entity `Region`**, nhưng nó được lấy từ **thuộc tính persistent `RegionalPricingRule.region`**. Vì FK `region_id` đã được ánh xạ trên entity value, `@MapKey(name = "region")` là cách thể hiện phù hợp.

Không nên thêm `@MapKeyJoinColumn(name = "region_id")` như thể đang khai báo một key FK độc lập trong join table, trừ khi bạn cố ý chọn một mô hình mapping khác và đã xác định rõ nơi lưu cột.

**Chọn đúng cơ chế dựa trên nguồn của key:**

- Key là **association/thuộc tính sẵn có bên trong entity value** → cân nhắc `@MapKey(name = "...")`.
- Key là **entity độc lập được lưu như một khóa của mapping Map**, ví dụ trong join table có FK key riêng → `@MapKeyJoinColumn`.
- Key là **basic value độc lập trong collection table** → `@MapKeyColumn`.

### 7.3. Thay đổi thuộc tính dùng làm key: bẫy đồng bộ

Giả sử `Warehouse.itemsBySku` được load:

```java
InventoryItem item = warehouse.getItemsBySku().get("SKU-OLD");
item.changeSku("SKU-NEW");
```

Sau khi sửa `item.sku`, **không nên giả định rằng key của Map trong bộ nhớ tự đổi** từ `"SKU-OLD"` sang `"SKU-NEW"`. Với `@MapKey` lấy từ property entity value, key trong Map thường không được đồng bộ tự động mỗi khi property thay đổi sau khi collection được dựng.

Hệ quả có thể là:

```java
warehouse.getItemsBySku().get("SKU-OLD"); // Có thể vẫn trả item.
warehouse.getItemsBySku().get("SKU-NEW"); // Có thể vẫn null trong context.
```

Dù database sau flush có `sku = "SKU-NEW"`, Map đã load có thể vẫn giữ cấu trúc key cũ. Vì vậy:

- Ưu tiên key property **ổn định/bất biến** trong phạm vi đời sống của Map.
- Nếu cần đổi key, có helper cập nhật cả thuộc tính `sku` và entry Map phù hợp.
- Rà soát unique constraint và khả năng trùng SKU.
- Nếu Map không thể đảm bảo đồng bộ hoặc nhu cầu thay key thường xuyên, cân nhắc query theo thuộc tính thay vì duy trì Map persistent.

Đây là khác biệt sâu hơn giữa “key là property của value entity” và “key là cột độc lập trong collection table”.

## 8. Tại sao entity key không thể được xử lý như value object tùy ý?

### 8.1. Entity có identity riêng

Với `Map<Region, PricingRule>`, key `Region` có:

- `@Id` và một identity trong JPA.
- Persistence lifecycle: transient, managed, detached hoặc removed.
- Có thể được tham chiếu bởi nhiều entity khác.
- Có thể được nạp qua lazy proxy/enhancement.
- Có thể có thuộc tính thay đổi nhưng vẫn là cùng entity nếu ID không đổi.

Trong khi đó, value object `FeatureCode` thường được nhận diện bằng nội dung `String value` và không có entity identity riêng.

Sự khác nhau này giải thích vì sao:

```java
Map<FeatureCode, Boolean> flags;      // Có thể dùng converter + @MapKeyColumn.
Map<Region, PricingRule> priceRules;  // Cần mapping entity key thích hợp.
```

không nên bị ánh xạ theo cùng một cách chỉ vì đều dùng `Map`.

### 8.2. Persist các entity key

Giả sử vừa tạo một `Region` chưa được persist:

```java
Region region = new Region("VN", "Việt Nam");
PricingRule rule = new PricingRule(
    "VN standard", new BigDecimal("1.0000")
);

PricingPlan plan = new PricingPlan("Public pricing");
plan.assignRule(region, rule);
```

Nếu mapping không có cascade cần thiết, chỉ gọi:

```java
entityManager.persist(plan);
```

**không bảo đảm** Region và PricingRule mới tự được persist; việc tạo row trong join table cần FK trỏ tới các row có identity hợp lệ. Trường hợp tham chiếu transient entity không được xử lý phù hợp có thể dẫn tới lỗi khi flush.

Hướng rõ ràng:

```java
entityManager.persist(region);
entityManager.persist(rule);
entityManager.persist(plan);

plan.assignRule(region, rule);
```

Đây là ví dụ trong một transaction; thứ tự SQL và thời điểm lấy ID tùy provider/chiến lược tạo ID. Trong nhiều hệ thống `Region` là danh mục có sẵn, service nên **tìm entity Region hiện hữu** theo ID hoặc code, thay vì tạo một Region mới mỗi lần thêm rule.

### 8.3. Không dựa vào cascade Map value để tạo entity key

Cascade cấu hình trên relationship Map trong JPA về nguyên tắc liên quan đến entity value của association, không nên suy ra từ đó rằng mọi **entity key** đều được persist/merge/remove tự động theo ý muốn.

Đặc biệt, **không cascade remove Region chỉ vì bỏ một key khỏi Map**. Region có thể được rất nhiều kế hoạch giá dùng chung.

Cách quản lý an toàn:

- `Region`: danh mục entity được quản lý độc lập.
- `PricingRule`: entity với lifecycle theo chính sách riêng.
- `PricingPlan.rulesByRegion`: thao tác thêm/xóa **liên kết** hoặc các value entity theo mapping cụ thể.
- `@MapKeyJoinColumn`: định nghĩa FK của key, không định nghĩa chính sách xóa key entity.

## 9. `Map.remove` xóa cái gì?

Cùng cú pháp Java nhưng tác động persistence khác nhau tùy mapping.

### 9.1. `@ElementCollection Map<String, String>`

```java
account.removePreference("theme");
```

Một entry basic biến mất; tương ứng row trong collection table `account_preference` được xóa. Không có entity độc lập tên `Preference` cần quản lý lifecycle.

### 9.2. `@OneToMany Map<Region, PricingRule>` với join table

```java
plan.removeRegion(region);
```

Câu lệnh mong đợi ở mức quan hệ là **xóa entry liên kết** trong `pricing_plan_rule` cho cặp `plan_id`/`region_id` tương ứng. Tác động tới row `pricing_rule` phụ thuộc lifecycle, ownership và cấu hình cascade/orphan removal của entity value.

Không nên diễn giải rằng xóa một Map entry nghĩa là:

```sql
DELETE FROM region WHERE id = ?;
```

vì `Region` là **entity key dùng chung**. Xóa nó có thể ảnh hưởng mọi plan tham chiếu Region đó và gây lỗi FK.

### 9.3. `@MapKey(name = "sku")` trên collection entity

Nếu xóa một item khỏi `Warehouse.itemsBySku`, tác động tới association `InventoryItem.warehouse` phụ thuộc vào owning side, cascade và orphan removal.

Với mapping hai chiều:

```java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, InventoryItem> itemsBySku;
```

`Warehouse.itemsBySku` là phía inverse của association. Nếu muốn chuyển một InventoryItem khỏi warehouse, code cần cập nhật **phía owner `InventoryItem.warehouse`**; chỉ xóa entry Map phía inverse không đủ để chỉ định thay đổi FK. Nếu entity con không thể tồn tại thiếu warehouse, cần quy tắc xóa/chuyển phù hợp với `nullable = false` và orphan removal khi có.

**Bài học:** Cần phân biệt **xóa Map entry**, **xóa association row**, **xóa entity value**, và **xóa entity key**. Đó là bốn thao tác có thể khác nhau.

## 10. Sự ổn định của entity key trong `HashMap`

### 10.1. Vì sao `equals` và `hashCode` quan trọng?

`HashMap` dựa vào `hashCode()` để chọn bucket và `equals()` để xác định key tương đương. Một key phải có hash ổn định trong suốt thời gian nằm trong Map.

Ví dụ nguy hiểm với entity có ID tự sinh:

```java
@Override
public int hashCode() {
    return Objects.hash(id);
}
```

Kịch bản:

1. Tạo `Region`, `id == null`.
2. Dùng Region làm key trong `HashMap`.
3. Persist Region; JPA cấp `id = 17`.
4. `hashCode` thay đổi vì ID thay đổi.
5. `map.get(region)` hoặc `map.remove(region)` có thể không tìm thấy entry đã chèn.

Đây là vấn đề **Java collection** trước khi là vấn đề SQL.

### 10.2. Những hướng thiết kế equality

Một số chiến lược có thể cân nhắc:

- **Business key bất biến, duy nhất:** ví dụ `Region.code` không đổi trong suốt vòng đời. Nếu thiết kế thật sự bảo đảm tính bất biến và duy nhất, có thể dùng business key cho equality.
- **Database identity:** so sánh theo ID khi đã được gán, nhưng cần xử lý entity chưa persist, hashCode ổn định và proxy type phù hợp.
- **Không dùng entity transient làm Map key:** chỉ đưa managed entity có ID ổn định vào Map, và không dựa vào value equality ngoài giới hạn lifecycle đã định.
- **Dùng basic key thay entity key:** nếu chỉ cần lookup bằng `regionCode` hoặc `regionId`, đôi khi `Map<String, PricingRule>` hoặc query theo region là đơn giản hơn, tùy ý nghĩa quan hệ.

Không có công thức `equals/hashCode` duy nhất tối ưu cho mọi entity JPA. Khi có Hibernate proxy hoặc nhiều persistence context, `getClass()`, `instanceof` và cách lấy ID cũng cần được xem xét trong chiến lược equality.

### 10.3. Không dùng thuộc tính mutable làm hash key

Nếu `Region` được hash theo `displayName`:

```java
region.rename("Việt Nam – khu vực 1");
```

sẽ làm hash thay đổi nếu tên hiển thị tham gia `hashCode`. Nên tránh dùng thuộc tính có thể chỉnh sửa làm thành phần equality của key.

Nếu khóa cần cập nhật thường xuyên, một basic key immutable hoặc một truy vấn tra cứu theo ID có thể phù hợp hơn việc giữ entity instance trong HashMap.

### 10.4. Entity khác instance nhưng cùng ID

Giả sử:

```java
Region managedRegion = entityManager.find(Region.class, 17L);
Region detachedRegion = ...; // Cũng biểu diễn Region(id=17).
```

Nếu equality của Region chỉ dùng object identity, `map.get(detachedRegion)` có thể không tìm thấy entry được nạp với `managedRegion`. Vì vậy, dù cả hai biểu diễn cùng database row, Map có thể xem chúng là hai key khác nhau.

Cách dùng an toàn thường là:

- Dùng entity key được nạp trong **cùng persistence context** với Map đang thao tác.
- Giải quyết request key ID thành managed reference phù hợp.
- Định nghĩa equality ổn định nếu ứng dụng cần tra cứu qua các instance khác nhau.
- Không tạo một Region mới chỉ gồm ID rồi coi nó đương nhiên là key tương đương trong mọi Map.

## 11. Cập nhật Map key không giống cập nhật Map value

Đối với Map basic:

```java
settings.put("theme", "light");
```

Thay value cho key `"theme"`.

Đổi khóa `theme` thành `ui-theme` nên được biểu diễn bằng:

```java
String value = settings.remove("theme");

if (value != null) {
    settings.put("ui-theme", value);
}
```

Nếu null là giá trị hợp lệ, cần kiểm tra `containsKey` trước khi remove để phân biệt “không tồn tại” với “tồn tại nhưng có giá trị null”.

Với entity key:

```java
PricingRule rule = rulesByRegion.remove(oldRegion);

if (rule != null) {
    rulesByRegion.put(newRegion, rule);
}
```

Điều này **thay đổi liên kết key Region**. Nó không nên được triển khai bằng việc sửa `oldRegion.id` hoặc đổi business key của Region để “biến” nó thành vùng khác.

**Định danh entity không nên bị tùy ý thay đổi.** Nếu cùng một PricingRule được áp dụng cho Region khác, hãy đổi Map entry/association theo nghiệp vụ; nếu cần giữ lịch sử, dùng entity liên kết chuyên dụng có thời điểm hiệu lực.

### 11.1. Thay value của cùng một entity key

```java
plan.assignRule(region, newRule);
```

Về trạng thái Map, Region vẫn là cùng key, nhưng value chuyển từ `oldRule` sang `newRule`. Khi persist, các thay đổi liên kết có thể tương ứng cập nhật cột `rule_id` trong join table hoặc thao tác xóa/chèn tùy provider.

Nếu `PricingRule` chỉ thuộc một plan và có ràng buộc `UNIQUE(rule_id)`, service cần kiểm soát việc tái sử dụng `newRule` đang thuộc plan khác.

### 11.2. Không sửa trực tiếp collection từ ngoài entity

Một setter như:

```java
public void setRulesByRegion(Map<Region, PricingRule> newRules) {
    this.rulesByRegion = newRules;
}
```

dễ khiến ứng dụng bỏ qua validation, quy tắc owner và cơ chế theo dõi collection của provider, đặc biệt nếu thay thế wrapper persistent đã được nạp.

Nên tạo phương thức `assignRule`, `removeRegion` và, nếu cần thay toàn bộ, dùng phương thức **tính chênh lệch** rồi thêm/xóa entry dưới sự kiểm soát của entity/service.

## 12. Đồng bộ toàn bộ tập khóa với yêu cầu từ API

Giả sử API gửi:

```json
{
  "planId": 5,
  "rules": [
    {"regionId": 2, "ruleId": 12},
    {"regionId": 3, "ruleId": 15}
  ]
}
```

Đây là **mô tả mong muốn của client**, không phải các entity JPA để `merge` trực tiếp.

Service cần:

1. Kiểm tra người gọi có quyền sửa plan.
2. Tải `PricingPlan` đang managed trong transaction.
3. Kiểm tra các `regionId` không trùng; mỗi Region là một key.
4. Tải Region hợp lệ và PricingRule hợp lệ theo ID.
5. Kiểm tra rule có được phép dùng trong plan/region.
6. So sánh các key hiện tại với tập key mong muốn.
7. Gọi helper remove/assign trên Map được JPA quản lý.
8. Commit transaction; xử lý unique/FK/locking conflict nếu có.

Đoạn mô tả giả sử có danh sách `DesiredRuleAssignment` mang region ID và rule ID:

```java
// Pseudocode ở tầng service.
Map<Long, Long> desiredRuleIdsByRegionId = ...;

// 1) Lấy plan managed.
// 2) Lấy Region và PricingRule managed theo ID.
// 3) Đọc tập key regionId đang có.
// 4) Xóa entry có regionId không nằm trong desired.
// 5) Put/replace entry có value khác.
// 6) Commit trong transaction.
```

Với Map key là entity, việc so sánh bằng ID trong tầng service có thể rõ ràng hơn việc so sánh detached key instances bằng `HashMap.equals`. Nhưng khi thao tác thực tế lên Map persistent, cần dùng những entity key phù hợp với quy tắc equality đã chọn.

### 12.1. Vì sao không `merge` nguyên object graph từ JSON?

Nếu client gửi nhiều object Region/PricingRule với các trường khác nhau, `merge` có thể làm nhiều thay đổi ngoài yêu cầu cập nhật liên kết, tùy cascade. Nó cũng khiến validation và authorization trở nên khó kiểm soát.

API nên truyền **ID hoặc mã tham chiếu**, còn service chuyển chúng thành entity reference an toàn và thao tác liên kết theo nghiệp vụ.

## 13. Ràng buộc database với khóa Map

### 13.1. Basic key: duy nhất theo owner và key

Với `account_preference`:

```sql
PRIMARY KEY (account_id, preference_key)
```

hoặc:

```sql
UNIQUE (account_id, preference_key)
```

đảm bảo một account không có hai preference cùng key.

### 13.2. Entity key: duy nhất theo owner và entity key FK

Với `pricing_plan_rule`:

```sql
UNIQUE (plan_id, region_id)
```

đảm bảo trong một plan, một Region chỉ có một PricingRule. Quan hệ này tương đương ràng buộc về **key uniqueness** của Map ở database.

### 13.3. Foreign key bảo vệ tham chiếu entity key

```sql
FOREIGN KEY (region_id) REFERENCES region(id)
```

bảo đảm key Region được tham chiếu tồn tại theo ràng buộc database. `@MapKeyJoinColumn` thể hiện ý định mapping entity key; schema migration phải duy trì FK phù hợp trong môi trường thực tế.

### 13.4. Có cần uniqueness của entity value không?

Điều đó phụ thuộc loại relationship của value:

- `@OneToMany`: một value entity thường thuộc một owner trong cùng quan hệ, nên cần xử lý phù hợp để không được liên kết lặp sang owner khác.
- `@ManyToMany`: value entity có thể được nhiều owner tham chiếu; bảng nối có cơ chế uniqueness khác.
- Khi cùng một value entity có thể gắn với nhiều key trong cùng Map, cần cân nhắc liệu điều đó có đúng nghiệp vụ và không mâu thuẫn với mapping multiplicity.

Không sao chép blindly mọi unique constraint giữa các model. Cần quyết định dựa trên tính một-nhiều/nhiều-nhiều của **entity value**, không chỉ từ kiểu `Map`.

### 13.5. Concurrency và race condition

Hai transaction có thể cùng thấy vùng `Region 2` chưa có rule trong `PricingPlan 5`, rồi đều thêm:

```text
Transaction A                       Transaction B
--------------------------------    --------------------------------
Tải Plan 5                          Tải Plan 5
Chưa có Region 2                    Chưa có Region 2
Put(Region 2, Rule A)               Put(Region 2, Rule B)
Flush                               Flush
COMMIT                              COMMIT hoặc conflict/ghi đè
```

Kết quả còn tùy isolation, strategy của provider và khóa đang có. Nhưng **`HashMap` trong mỗi transaction không thể đảm bảo duy nhất giữa hai transaction**.

Cần ràng buộc DB `UNIQUE(plan_id, region_id)`, và nếu nghiệp vụ cần tránh lost update hoặc áp quy tắc version, xem xét `@Version`, locking/transaction isolation phù hợp.

## 14. `@MapKeyJoinColumns` khi entity key có khóa ghép

Ví dụ entity `TaxJurisdiction` được định danh bởi hai thành phần:

- `countryCode`.
- `subdivisionCode`.

Khóa ghép có thể biểu diễn bằng `@EmbeddedId`:

```java
@Embeddable
public class TaxJurisdictionId
        implements java.io.Serializable {

    private String countryCode;
    private String subdivisionCode;

    protected TaxJurisdictionId() {
    }

    public TaxJurisdictionId(
            String countryCode,
            String subdivisionCode
    ) {
        this.countryCode = countryCode;
        this.subdivisionCode = subdivisionCode;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public String getSubdivisionCode() {
        return subdivisionCode;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof TaxJurisdictionId other)) return false;
        return java.util.Objects.equals(countryCode, other.countryCode)
            && java.util.Objects.equals(
                subdivisionCode, other.subdivisionCode
            );
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(
            countryCode, subdivisionCode
        );
    }
}
```

Entity key:

```java
@Entity
public class TaxJurisdiction {

    @EmbeddedId
    private TaxJurisdictionId id;

    private String name;

    protected TaxJurisdiction() {
    }
}
```

Khi Map có key `TaxJurisdiction` là entity với **hai cột định danh**, join table có thể cần **hai FK columns**. Jakarta Persistence cung cấp `@MapKeyJoinColumns` để khai báo nhiều cột key join:

```java
@OneToMany
@JoinTable(
    name = "plan_tax_rule",
    joinColumns = @JoinColumn(name = "plan_id"),
    inverseJoinColumns = @JoinColumn(name = "rule_id")
)
@MapKeyJoinColumns({
    @MapKeyJoinColumn(
        name = "key_country_code",
        referencedColumnName = "countryCode"
    ),
    @MapKeyJoinColumn(
        name = "key_subdivision_code",
        referencedColumnName = "subdivisionCode"
    )
})
private Map<TaxJurisdiction, PricingRule> taxRules;
```

Đoạn này là **mẫu cấu trúc annotation**. Tên `referencedColumnName` phải khớp **tên cột database được ánh xạ trong entity key**, không chỉ tên field Java. Vì vậy nếu `TaxJurisdictionId` khai báo `@Column(name = "country_code")` và `@Column(name = "subdivision_code")`, thì phải dùng các tên cột đó tương ứng:

```java
@MapKeyJoinColumns({
    @MapKeyJoinColumn(
        name = "key_country_code",
        referencedColumnName = "country_code"
    ),
    @MapKeyJoinColumn(
        name = "key_subdivision_code",
        referencedColumnName = "subdivision_code"
    )
})
```

Khi dùng composite key, cả FK nhiều cột, thứ tự, nullable và unique constraints cần nhất quán với schema. Không dùng một `@MapKeyJoinColumn` đơn lẻ để tham chiếu một entity key có khóa ghép rồi giả định JPA sẽ tự chọn cột còn lại theo ý muốn.

### 14.1. Không nhầm `@MapKeyJoinColumns` với `@JoinColumns`

- `@JoinColumns` thường cấu hình **nhiều cột FK của một association**.
- `@MapKeyJoinColumns` xác định **nhiều cột của FK dùng cho entity key của Map**.
- `@JoinTable.inverseJoinColumns` vẫn có vai trò liên kết entity **value** trong một association qua join table.

Một Map có **entity key composite** và **entity value composite** có thể cần nhiều nhóm cột khác nhau; luôn vẽ schema trước để không đảo vai trò key/value.

## 15. Một Map key có thể là embeddable không?

Có những Map muốn dùng key là một **value object gồm nhiều thành phần**, chẳng hạn:

```java
@Embeddable
public class LocaleKey {
    private String language;
    private String country;

    protected LocaleKey() {
    }

    public LocaleKey(String language, String country) {
        this.language = language;
        this.country = country;
    }

    // Getter, equals, hashCode được định nghĩa phù hợp.
}
```

Nếu map key là **embeddable** thay vì entity, bạn **không** dùng `@MapKeyJoinColumn` chỉ vì nó có nhiều field. Embeddable key có ngữ nghĩa **giá trị**, không có entity ID riêng.

Mapping các cột của embeddable key có thể dùng quy tắc attribute overrides dành cho Map key với đường dẫn `key.<attribute>`, ví dụ minh họa:

```java
@ElementCollection
@CollectionTable(
    name = "localized_setting",
    joinColumns = @JoinColumn(name = "owner_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "key.language",
        column = @Column(name = "language_code")
    ),
    @AttributeOverride(
        name = "key.country",
        column = @Column(name = "country_code")
    )
})
@Column(name = "localized_value")
private Map<LocaleKey, String> localizedSettings =
    new HashMap<>();
```

Ý nghĩa:

- `LocaleKey` được ánh xạ thành **hai basic columns**.
- `@AttributeOverride(name = "key.language", ...)` và `key.country` chỉ tới thuộc tính **của map key embeddable**.
- Không có bảng entity `LocaleKey` và không có FK tới nó.
- Cần unique key theo `owner_id, language_code, country_code` nếu nghiệp vụ yêu cầu một giá trị trên mỗi locale.

Đây là một khác biệt quan trọng: **key nhiều cột** không đồng nghĩa **key là entity**.

Nếu key là entity có khóa ghép, hãy dùng entity identity/`@MapKeyJoinColumns` theo cấu trúc phù hợp; nếu key là embeddable, dùng mapping các thuộc tính giá trị của embeddable.

## 16. `@MapKeyClass` và thông tin generic type

Trong Java, nên khai báo Map với generic:

```java
private Map<Region, PricingRule> rulesByRegion;
```

Khi đó JPA thường có thể suy ra K là `Region` và V là `PricingRule` từ metadata Java.

`@MapKeyClass` là annotation liên quan đến kiểu key trong một số mapping khi generic type không cung cấp đủ thông tin. Nó **không thay thế** `@MapKeyColumn` hoặc `@MapKeyJoinColumn`:

- `@MapKeyClass` nói về **Java class của key**.
- `@MapKeyColumn` nói về **cột key basic**.
- `@MapKeyJoinColumn` nói về **FK key entity**.
- `@MapKey` nói về **thuộc tính của entity value được dùng làm key**.

Nên ưu tiên generic rõ ràng trong code Java hiện đại. Việc dùng raw `Map` làm mất type-safety và khiến người đọc/provider khó xác định mapping hơn.

## 17. Fetching và hiệu năng với Map

### 17.1. Map là persistent collection

Một Map được ánh xạ bằng `@ElementCollection`, `@OneToMany` hoặc `@ManyToMany` là **collection-valued attribute** trong JPA.

Ví dụ:

```java
PricingPlan plan =
    entityManager.find(PricingPlan.class, 5L);

// Tùy fetch strategy/provider, truy cập collection
// có thể kích hoạt SQL:
Map<Region, PricingRule> entries =
    plan.getRulesByRegion();
```

Mặc định, các collection relationship/element collection thường dùng `FetchType.LAZY` theo JPA, nhưng LAZY là một fetch hint và chi tiết SQL phụ thuộc provider. Với entity key, việc truy cập thuộc tính của key như `region.getCode()` có thể cần thêm SQL nếu key reference chưa khởi tạo đầy đủ.

### 17.2. Không truy cập hàng loạt Map một cách vô thức

```java
List<PricingPlan> plans = entityManager.createQuery(
    "select p from PricingPlan p",
    PricingPlan.class
).getResultList();

for (PricingPlan plan : plans) {
    System.out.println(plan.getRulesByRegion().size());
}
```

Nếu mỗi Map được tải riêng, đây có thể là **N+1 SELECT**. Với Map có entity key và value đều cần đọc, số query bổ sung có thể phức tạp hơn do các entity liên kết.

Hướng xử lý theo use case:

- Query projection lấy dữ liệu đúng cột cần dùng.
- `JOIN FETCH` nếu thật sự cần toàn bộ Map và có lượng row hợp lý.
- Entity graph theo nhu cầu tải.
- Batch fetching khi provider hỗ trợ.
- Phân trang các entity chủ và tải collection theo chiến lược rõ ràng.

### 17.3. Fetch join có thể nhân bản row

Ví dụ:

```java
List<PricingPlan> plans = entityManager.createQuery(
    """
    select distinct p
    from PricingPlan p
    left join fetch p.rulesByRegion
    where p.id in :ids
    """,
    PricingPlan.class
)
.setParameter("ids", List.of(5L, 6L))
.getResultList();
```

Một plan có 20 key có thể xuất hiện trong 20 SQL result rows. Provider xử lý rows để dựng collection, nhưng lượng dữ liệu trao đổi có thể lớn. Fetch join collection với pagination cần thận trọng vì giới hạn SQL không còn tương ứng đơn giản với số entity chủ.

**Đừng dùng EAGER mọi nơi chỉ để tránh N+1**. EAGER có thể gây tải dữ liệu không dùng đến hoặc secondary SELECT. Cần quan sát SQL thật và chọn fetch plan phù hợp.

### 17.4. Không trả entity Map trực tiếp qua JSON

Nếu API serialize một entity có Map key là entity:

```java
Map<Region, PricingRule> rulesByRegion;
```

có thể gặp vấn đề:

- JSON object key theo chuẩn biểu diễn tên property bằng chuỗi, không phải đối tượng entity Java tùy ý.
- Serializer cần chọn cách chuyển Region thành chuỗi, có thể gọi `toString` hoặc cơ chế đặc thù, không ổn định như contract API.
- Truy cập key/value có thể kích hoạt lazy loading.
- Có thể tạo vòng lặp quan hệ khi entity key/value tham chiếu ngược.
- Lộ các thuộc tính không định công bố ra ngoài.

API nên dùng DTO như:

```java
public record PricingRuleResponse(
    Long regionId,
    String regionCode,
    Long ruleId,
    BigDecimal multiplier
) { }

public record PricingPlanResponse(
    Long planId,
    List<PricingRuleResponse> rules
) { }
```

Tách representation HTTP khỏi persistent Map giúp kiểm soát rõ nội dung và tránh phụ thuộc vào cách JPA provider xây các entity key.

## 18. Map và quyền sở hữu association

### 18.1. `@OneToMany(mappedBy = ...)` dùng Map vẫn là inverse side

Ví dụ trước:

```java
@OneToMany(mappedBy = "warehouse")
@MapKey(name = "sku")
private Map<String, InventoryItem> itemsBySku;
```

Owner của **association Warehouse–InventoryItem** là:

```java
@ManyToOne
@JoinColumn(name = "warehouse_id")
private Warehouse warehouse;
```

`@MapKey(name = "sku")` chỉ xác định **key** cho Map, không chuyển ownership của FK về `Warehouse.itemsBySku`.

Nếu code chỉ làm:

```java
warehouse.getMutableItemsBySku().put(item.getSku(), item);
```

mà không gán `item.warehouse = warehouse`, liên kết SQL có thể không được lưu đúng. Nên tạo helper cập nhật owning side và inverse Map, kiểm tra trùng SKU và các ràng buộc.

### 18.2. Map dùng join table một chiều có owner ở collection

Với:

```java
@OneToMany
@JoinTable(...)
@MapKeyJoinColumn(...)
private Map<Region, PricingRule> rulesByRegion;
```

collection là phía khai báo association qua join table. Thêm/xóa entry ở collection này có ý nghĩa ghi/xóa join row, khác trường hợp inverse Map dùng `mappedBy`.

### 18.3. Không trộn hai nghĩa của “key”

Cần phân biệt:

- **Map key `K`:** khóa tra cứu trong Java Map.
- **Primary key của entity:** `@Id`.
- **Foreign key trong SQL:** cột tham chiếu bảng khác.
- **Khóa chính của join table:** một hoặc nhiều cột dùng để nhận diện row liên kết.
- **Business key:** mã có ý nghĩa nghiệp vụ, ví dụ `Region.code`.

Một entity key `Region` có primary key `id`, rồi được join table tham chiếu bằng FK `region_id`, và được Java Map dùng làm **key object**. Cả ba lớp khái niệm có liên quan nhưng không đồng nhất.

## 19. Khi nào nên bỏ Map và dùng entity liên kết?

Một Map như:

```java
Map<Region, PricingRule> rulesByRegion;
```

hợp lý khi mỗi cặp plan–region chỉ cần liên kết tới một PricingRule. Nhưng nếu bản thân việc áp dụng rule cho region còn có:

- `effectiveFrom` và `effectiveTo`.
- Người phê duyệt.
- Trạng thái chờ duyệt.
- Thứ tự ưu tiên.
- Phiên bản lịch sử.
- Điều kiện giá theo kênh bán.
- Nhiều rule đồng thời cho cùng một region.

thì bảng nối đã mang **dữ liệu nghiệp vụ riêng**.

Ví dụ:

```text
pricing_plan_region_rule
+---------------+----------------+
| id (PK)       |                |
| plan_id (FK)  |                |
| region_id (FK)|                |
| rule_id (FK)  |                |
| valid_from    |                |
| valid_to      |                |
| priority      |                |
| status        |                |
+---------------+----------------+
```

Nên cân nhắc entity:

```java
@Entity
@Table(name = "pricing_plan_region_rule")
public class PricingPlanRegionRule {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "plan_id")
    private PricingPlan plan;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "region_id")
    private Region region;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "rule_id")
    private PricingRule rule;

    private java.time.LocalDate validFrom;
    private java.time.LocalDate validTo;
    private int priority;

    protected PricingPlanRegionRule() {
    }
}
```

Khi có nhiều rule trên một region theo thời gian, một Map đơn `Region -> PricingRule` không thể tự diễn đạt toàn bộ lịch sử. Có thể dùng `List<PricingPlanRegionRule>`, query theo vùng/thời gian hoặc cấu trúc domain riêng.

**Không cố nhồi metadata của join row vào `@MapKeyJoinColumn`.** Annotation này chỉ định FK của entity key, không tạo entity cho chính liên kết.

## 20. Các sai lầm thường gặp

### 20.1. “`@MapKeyColumn` là cách ánh xạ khóa Map cho mọi kiểu K”

**Sai.** Nó phù hợp với cột basic key. Nếu K là entity `Region`, cần mapping entity-key như `@MapKeyJoinColumn` hoặc `@MapKey` theo nguồn của key.

### 20.2. “`@MapKeyJoinColumn` là cột tham chiếu entity value”

**Sai.** Nó dành cho **entity key**. Trong `@JoinTable`, `inverseJoinColumns` có thể ánh xạ FK tới entity value, còn `@MapKeyJoinColumn` ánh xạ FK tới entity key.

### 20.3. “Map có hai entity thì chỉ cần hai FK”

Chưa chắc. Trong ví dụ `PricingPlan` có `Map<Region, PricingRule>` dùng join table, hàng liên kết chứa FK tới **plan chủ**, **region key** và **pricing rule value**: ba vai trò tham chiếu khác nhau.

### 20.4. “`@MapKey(name = "sku")` tạo thêm một cột map key”

Không. Nó lấy key từ **thuộc tính persistent `sku` của entity value**. Nếu cột `sku` đã tồn tại, JPA có thể sử dụng chính nó làm key khi dựng Map.

### 20.5. “Sửa `item.sku` thì Map key tự thay đổi ngay”

Không nên giả định. Key của Map đã được dựng từ property value có thể **không tự đồng bộ** khi property thay đổi. Cần helper hoặc key ổn định.

### 20.6. “Map key là entity thì khóa không bao giờ đổi”

Identity của entity ổn định, nhưng object có thể có `hashCode` dựa trên thuộc tính mutable hoặc ID chưa được cấp. Dùng entity như key trong `HashMap` đòi hỏi equality/hash ổn định.

### 20.7. “Gắn `CascadeType.ALL` sẽ tự quản lý cả entity key và entity value”

Không nên dựa vào giả định đó. Cascade relationship Map cần được hiểu theo quy tắc cascade tới **giá trị entity**; entity key danh mục thường được quản lý riêng. Đặc biệt không tự xóa key Region khi remove entry.

### 20.8. “Xóa Map entry chắc chắn xóa entity value và key”

Sai. Với `@ElementCollection` là xóa collection value row; với join table là xóa liên kết theo mapping; entity key không tự bị xóa. Entity value có bị xóa hay không còn phụ thuộc cascade/orphan removal và nghiệp vụ.

### 20.9. “Đã dùng `HashMap` nên DB không cần UNIQUE”

Sai. `HashMap` chỉ ngăn trùng trong một instance Java theo equality. DB cần unique constraint để bảo vệ dữ liệu khi nhiều transaction cùng ghi.

### 20.10. “`@MapKeyJoinColumn` giống hệt `@JoinColumn` của chủ Map”

Không. `@JoinColumn` trong `@JoinTable.joinColumns` tham chiếu **entity chủ Map**; `@MapKeyJoinColumn` tham chiếu **entity key**. Nhầm hai loại FK dẫn tới schema hoặc SQL sai.

### 20.11. “Key entity phải được serialize thành một JSON object key”

Không. Map Java có thể dùng object làm key, JSON object thường cần tên property dạng chuỗi. Cần DTO/representation phù hợp ở biên API.

### 20.12. “`Map.put` luôn tạo đúng một INSERT hoặc UPDATE”

Không được JPA bảo đảm. Provider quyết định chiến lược dirty checking/collection synchronization. Chỉ nên kỳ vọng trạng thái bền vững sau flush/commit hợp lệ, không phụ thuộc một số statement cố định.

### 20.13. “Đặt `mappedBy` lên Map là đã đồng bộ cả hai phía”

Không. `mappedBy` xác định phía inverse của association; code vẫn phải đồng bộ owning reference/collection và inverse Map khi thay đổi liên kết hai chiều.

### 20.14. “Key là embeddable nhiều cột thì dùng `@MapKeyJoinColumns`”

Không. `@MapKeyJoinColumns` dành cho khóa **entity có composite identifier**. Key embeddable cần ánh xạ các thuộc tính basic của value object, có thể qua `@AttributeOverride` với đường dẫn `key.*`.

### 20.15. “Có `@MapKeyJoinColumn` là JDBC/JPA tự tìm entity key hợp lệ từ mã người dùng”

Không. Cần truy vấn hoặc lấy managed reference theo identity, kiểm tra tồn tại/authorization và xử lý FK. Annotation chỉ khai báo mapping, không thực hiện business validation.

## 21. Quy trình thiết kế một Map trong JPA

Có thể dùng trình tự dưới đây khi gặp một `Map<K, V>` mới:

1. **Xác định Map phục vụ nghiệp vụ gì.** Có thực sự cần lookup theo key, hay chỉ cần List/Set và một query?
2. **Phân loại K.** K là basic, enum, value object/embeddable hay entity?
3. **Phân loại V.** V là basic/embeddable hay entity có identity?
4. **Xác định nơi tồn tại của key.** Key là cột riêng của collection table, FK riêng tới entity, hay thuộc tính đã ánh xạ của entity value?
5. **Chọn annotation.** `@MapKeyColumn`, `@MapKeyJoinColumn` hoặc `@MapKey(name=...)` theo đúng mô hình.
6. **Chọn mapping collection.** `@ElementCollection`, `@OneToMany`, `@ManyToMany`; quyết định có `@CollectionTable`/`@JoinTable` hay FK ở bảng value.
7. **Vẽ bảng và các FK.** Xác định cột owner, key, value; đừng dựa chỉ vào tên annotation.
8. **Thiết lập ràng buộc duy nhất.** Một chủ sở hữu + một key chỉ có tối đa một value nếu đúng ngữ nghĩa Map.
9. **Thiết kế equality ổn định.** Đặc biệt với entity key và ID được sinh sau persist.
10. **Xác định cách cập nhật.** Thao tác trên managed entity trong transaction; dùng helper, tránh thay trực tiếp Map từ bên ngoài.
11. **Quy định vòng đời.** Xóa entry có xóa value không? Key entity có phải danh mục dùng chung không? Có cascade hay orphan removal không?
12. **Đo fetch và SQL thực tế.** Xem kích thước Map, lazy loading, join fetching và giới hạn DTO/API.
13. **Khi liên kết có metadata riêng,** đánh giá chuyển sang một entity liên kết thay vì ép vào Map đơn.

Sơ đồ quyết định:

```text
                      Map<K, V> persistent
                               |
                               v
                         K là entity?
                         /           \
                       Không         Có
                        |             |
                        v             v
                 Key là basic      Key lấy từ property
                 hay embeddable    của entity value V?
                        |             /        \
                        |           Có         Không
                        v            |           |
               Basic key column      v           v
               @MapKeyColumn      @MapKey     @MapKeyJoinColumn
               (hoặc overrides)   (name=...)  (FK key entity)
                        \            |           /
                         \           |          /
                          +----------+---------+
                                     |
                                     v
                         V là basic/embeddable
                         hay entity association?
                                     |
                         +-----------+-----------+
                         |                       |
                         v                       v
                  @ElementCollection      @OneToMany / @ManyToMany
                         |                       |
                         v                       v
                  @CollectionTable         @JoinTable hoặc
                  nếu cần                  FK/value table phù hợp
                         \                       /
                          +----------+----------+
                                     |
                                     v
                          Unique/FK constraints,
                          equality, transaction,
                          fetch và lifecycle
```

## 22. Bài tập vận dụng

### Bài tập 1: Đọc `@MapKeyColumn`

Cho:

```java
@ElementCollection
@CollectionTable(
    name = "product_attribute",
    joinColumns = @JoinColumn(name = "product_id")
)
@MapKeyColumn(name = "attribute_name")
@Column(name = "attribute_value")
private Map<String, String> attributes;
```

**Câu hỏi:** Cột nào là khóa Map, cột nào là value, cột nào là FK tới chủ sở hữu?

**Gợi ý:** `attribute_name` là key; `attribute_value` là value; `product_id` liên kết row collection với Product. Không cột nào trong `attribute_name` tự tham chiếu entity khác chỉ nhờ `@MapKeyColumn`.

### Bài tập 2: Entity làm key

Map:

```java
private Map<Region, PricingRule> rulesByRegion;
```

`Region` và `PricingRule` đều là entity, `PricingPlan` là chủ Map; schema có join table `plan_rule` với cột `plan_id`, `region_id` và `rule_id`.

**Câu hỏi:** Annotation nào ánh xạ `region_id`? Annotation nào ánh xạ `rule_id`?

**Gợi ý:** `@MapKeyJoinColumn(name = "region_id")` ánh xạ entity **key**. `@JoinTable.inverseJoinColumns = @JoinColumn(name = "rule_id")` ánh xạ entity **value**.

### Bài tập 3: Phân biệt `@MapKey`

```java
@OneToMany(mappedBy = "department")
@MapKey(name = "employeeCode")
private Map<String, Employee> employeesByCode;
```

**Câu hỏi:** Có nhất thiết một cột `map_key` riêng không?

**Gợi ý:** Không. Key lấy từ thuộc tính `Employee.employeeCode` đã persistent. Mapping giá trị `Employee.department` nắm FK tới Department.

### Bài tập 4: Sửa key property sau khi load

`employeesByCode` chứa `"EMP-01" -> Employee X`. Code đổi `X.employeeCode` thành `"EMP-99"`.

**Câu hỏi:** `employeesByCode.get("EMP-99")` có chắc trả X ngay không?

**Gợi ý:** Không. JPA không bảo đảm key trong Map đang loaded tự đổi theo property mới. Dùng helper cập nhật key/entry có kiểm soát hoặc tránh sửa thuộc tính key.

### Bài tập 5: Key enum

Map `Map<CurrencyCode, BigDecimal> rates`, database cần lưu ký hiệu `USD`, `VND`.

**Câu hỏi:** Annotation nào dành cho kiểu enum ở vị trí key?

**Gợi ý:** `@MapKeyEnumerated(EnumType.STRING)` kết hợp `@MapKeyColumn` nếu muốn đặt tên cột key rõ ràng. Không nhầm với `@Enumerated` trên một thuộc tính enum đơn lẻ.

### Bài tập 6: Key value object với converter

`FeatureCode` là record bọc `String`, dùng làm key của `Map<FeatureCode, Boolean>`.

**Câu hỏi:** Có cần entity `FeatureCode` để dùng `@MapKeyJoinColumn` không?

**Gợi ý:** Không. Nếu là basic value type và có converter phù hợp, dùng `@MapKeyColumn` cho cột key và `@Convert(attributeName = "key", converter=...)` cho representation.

### Bài tập 7: Composite key entity

`TaxJurisdiction` có identity gồm `country_code`, `subdivision_code`. Map dùng `TaxJurisdiction` làm entity key.

**Câu hỏi:** Dùng `@MapKeyJoinColumn` một cột là đủ không?

**Gợi ý:** Cần ánh xạ đầy đủ các cột FK của composite identity; có thể dùng `@MapKeyJoinColumns` với từng `referencedColumnName` tương ứng các cột SQL của entity key.

### Bài tập 8: Key embeddable

`LocaleKey(language, country)` là `@Embeddable`, không phải entity. Map `Map<LocaleKey, String>` cần hai cột khóa.

**Câu hỏi:** Nên dùng `@MapKeyJoinColumns` hay attribute overrides?

**Gợi ý:** Dùng mapping embeddable với `@AttributeOverride(name = "key.language", ...)` và `key.country`; không dùng entity-key FK annotation nếu không có entity key.

### Bài tập 9: Concurrent update

Hai request cùng `put` một Region key cho cùng PricingPlan, nhưng đặt hai PricingRule khác nhau.

**Câu hỏi:** Map Java có bảo đảm DB chỉ còn một row đúng theo lựa chọn mong muốn không?

**Gợi ý:** Không. Mỗi transaction có Map riêng; cần unique constraint `(plan_id, region_id)`, chiến lược locking/concurrency và quy tắc giải quyết xung đột.

### Bài tập 10: Xóa entry

`Map<Region, PricingRule>` chứa Region `VN`. Service gọi `removeRegion(vn)`.

**Câu hỏi:** Entity `Region` có bị xóa không?

**Gợi ý:** Không mặc định. Thao tác xóa liên kết Map trong join table; Region là entity key có vòng đời riêng. Có xóa PricingRule value hay không phụ thuộc mapping/lifecycle, không được suy ra chỉ từ `Map.remove`.

### Bài tập 11: Chọn Map hay entity liên kết

Một plan có **nhiều rule cho cùng Region**, mỗi rule có `validFrom` và `validTo`.

**Câu hỏi:** `Map<Region, PricingRule>` có biểu diễn đủ không?

**Gợi ý:** Không, một Map key chỉ trỏ tới một value trong mỗi thời điểm trong bộ nhớ. Cân nhắc entity liên kết `PricingPlanRegionRule` mang region, rule và khoảng hiệu lực, hoặc mô hình truy vấn khác.

### Bài tập 12: Phát hiện N+1

Service tải 200 PricingPlan rồi duyệt `rulesByRegion` của từng plan để tính số rule.

**Câu hỏi:** Vì sao có thể phát sinh nhiều SQL và cách thay thế đơn giản nếu chỉ cần số lượng?

**Gợi ý:** Map là lazy collection; mỗi plan có thể kích hoạt truy vấn riêng. Nếu chỉ cần count, dùng JPQL aggregate/projection theo plan thay vì load toàn bộ Map và từng entity key/value.

## 23. Ghi nhớ cốt lõi

- **`@MapKeyColumn` dành cho cột key dạng basic/value**, ví dụ `Map<String, String>` ở `@ElementCollection`.
- **`@MapKeyJoinColumn` dành cho key là entity**, ánh xạ FK tới entity key trong bảng liên kết phù hợp.
- **`@MapKey(name = "...")` dùng thuộc tính persistent của entity value làm Map key**; key không nhất thiết có một cột riêng.
- **`@MapKeyEnumerated`, `@MapKeyTemporal`, `@Convert(attributeName = "key")`** có vai trò riêng đối với những kiểu key basic; không đánh đồng chúng với entity-key association.
- **Một Map có thể gồm entity chủ, entity key và entity value**: cần hiểu cả ba vai trò FK nếu dùng join table.
- **Entity key có identity và lifecycle riêng.** Xóa Map entry không mặc định xóa entity key.
- **Tính ổn định của `equals/hashCode` rất quan trọng**, nhất là khi key là entity có ID tự sinh, proxy hoặc thuộc tính mutable.
- **Ràng buộc UNIQUE/PK/FK ở DB vẫn cần thiết** để bảo vệ semantics một key–một value khi có nhiều transaction.
- **Thay property làm key qua `@MapKey` không tự đồng bộ key của Map đang loaded**; nên dùng key ổn định hoặc helper có kiểm soát.
- **Quan hệ một-nhiều hai chiều vẫn có owner/inverse side**: `@MapKey` không thay vai trò `mappedBy` và `@ManyToOne`.
- **Khi liên kết có dữ liệu riêng hoặc nhiều value cho một key**, cần cân nhắc entity liên kết thay vì cố ép vào một Map đơn.
- **Fetch và API là các quyết định tách biệt**: Map key entity có thể gây thêm SQL và không nên serialize thẳng thành JSON object key.

Khi gặp một thuộc tính `Map<K, V>` trong JPA, hãy **vẽ ra bảng lưu entry và khoanh rõ cột dành cho chủ Map, cột key K và cột/value V**. Nếu key là dữ liệu basic, nghĩ tới `@MapKeyColumn`; nếu key là entity độc lập, nghĩ tới `@MapKeyJoinColumn`; nếu key là thuộc tính của entity value, nghĩ tới `@MapKey`. Cách phân loại này giúp chọn đúng annotation, tránh nhầm khóa Map với khóa chính/khóa ngoại và duy trì dữ liệu nhất quán giữa Java và database.
