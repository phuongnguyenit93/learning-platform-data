# Ánh xạ số nguyên, số thập phân và `precision`, `scale` trong JPA

## 1. Từ số trong Java đến cột số trong cơ sở dữ liệu

Khi xây dựng ứng dụng sử dụng **Jakarta Persistence (JPA)**, một thuộc tính kiểu số trong entity được lưu vào cột có kiểu dữ liệu số tương ứng của cơ sở dữ liệu quan hệ. Việc lựa chọn kiểu Java, kiểu SQL và giới hạn chữ số ảnh hưởng trực tiếp đến:

- **Khoảng giá trị** có thể lưu: số lượng hàng tồn, số lần truy cập, mã định danh, số tiền.
- **Độ chính xác** khi tính toán: đặc biệt quan trọng với tiền tệ, thuế, tỷ lệ và các đại lượng cần kết quả thập phân chính xác.
- **Tính toàn vẹn dữ liệu**: giá trị vượt giới hạn, có quá nhiều chữ số thập phân hoặc không phù hợp với ràng buộc database có thể bị từ chối hoặc được xử lý theo quy tắc của hệ quản trị.
- **Khả năng tương thích giữa các database**: cú pháp và phạm vi kiểu số có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle, H2 và các hệ khác.

JPA sử dụng **provider** (như Hibernate ORM hoặc EclipseLink) để chuyển đổi state của entity thành dữ liệu JDBC và SQL. Trong entity, ta khai báo kiểu Java và có thể bổ sung metadata ánh xạ bằng `@Column`:

```java
@Column(name = "unit_price", precision = 15, scale = 2)
private BigDecimal unitPrice;
```

Đoạn mã thể hiện ý định dùng cột **số thập phân chính xác** với tổng cộng 15 chữ số, trong đó tối đa 2 chữ số nằm sau dấu thập phân. Kiểu SQL thực tế do provider và database dialect quyết định; thường tương đương `DECIMAL(15, 2)` hoặc `NUMERIC(15, 2)`.

Trong bài này, cú pháp API dùng gói `jakarta.persistence` của Jakarta Persistence hiện đại. Các project JPA cũ có thể dùng `javax.persistence`; nguyên tắc ánh xạ kiểu số về cơ bản tương tự, nhưng dependency phải nhất quán với phiên bản provider của project.

## 2. Ánh xạ nhóm số nguyên

### 2.1. Các kiểu nguyên thông dụng

Java cung cấp các kiểu nguyên primitive và wrapper. JPA có thể lưu chúng dưới dạng cột SQL nguyên hoặc kiểu numeric phù hợp:

| Kiểu thuộc tính Java | Kiểu SQL thường gặp | Ứng dụng tiêu biểu | Ghi chú |
|---|---|---|---|
| `byte`, `Byte` | `SMALLINT` hoặc kiểu nguyên nhỏ do dialect chọn | Cờ/trạng thái mã hóa nhỏ, số đếm nhỏ | Kiểu `TINYINT` có ở một số database; ánh xạ cụ thể không đồng nhất. |
| `short`, `Short` | `SMALLINT` | Số lượng nhỏ, mức độ | Giới hạn Java từ -32.768 đến 32.767. |
| `int`, `Integer` | `INTEGER` / `INT` | Số lượng, vị trí, số lần | Giới hạn Java từ -2.147.483.648 đến 2.147.483.647. |
| `long`, `Long` | `BIGINT` | ID, bộ đếm lớn | Java `long` là số nguyên 64 bit có dấu. |
| `BigInteger` | `NUMERIC` / `DECIMAL` hoặc kiểu thích hợp do provider chọn | Số nguyên vượt phạm vi `long` | Kiểu SQL và phạm vi thực tế phải được cấu hình/kiểm tra. |

Đây là các kiểu SQL **thường gặp**, không phải cam kết JPA sẽ luôn tạo đúng cùng một tên kiểu trên mọi database. Ví dụ provider có thể chọn `SMALLINT` thay vì `TINYINT` cho `Byte`, hoặc ánh xạ `BigInteger` sang kiểu số chính xác của dialect.

Giới hạn của `long` là từ **-9.223.372.036.854.775.808** đến **9.223.372.036.854.775.807**. Ngay cả nếu một cột SQL có 19 chữ số biểu diễn, giá trị nó cho phép còn phụ thuộc chính xác vào loại cột và database; `BIGINT` 64 bit có dấu không chứa được mọi số nguyên gồm 19 chữ số.

### 2.2. Primitive và wrapper: phân biệt `null`

Với thuộc tính:

```java
private int quantity;
```

`quantity` luôn có một giá trị Java, mặc định là `0` nếu chưa gán. Trong khi đó:

```java
private Integer quantity;
```

có thể chứa `null`, cho phép phân biệt **chưa có dữ liệu** với **số lượng bằng không**. Nếu dữ liệu bắt buộc có giá trị, khai báo:

```java
@Column(name = "quantity", nullable = false)
private Integer quantity;
```

`nullable = false` mô tả ràng buộc null của cột để phục vụ schema generation và metadata ánh xạ. Nó không thay thế mọi cơ chế kiểm tra đầu vào ở tầng Java. Nếu dự án dùng Jakarta Bean Validation, có thể bổ sung `@NotNull` hoặc `@Min(0)` để xác thực theo quy tắc nghiệp vụ.

**Chọn primitive hay wrapper theo ngữ nghĩa dữ liệu**, không chỉ vì cả hai ánh xạ được sang `INTEGER`. Với ID tự sinh thường dùng `Long` thay vì `long`: giá trị `null` của object mới có ích để biểu diễn định danh chưa được database cấp.

### 2.3. Ví dụ ánh xạ số lượng và mã định danh

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    @Column(name = "reorder_threshold", nullable = false)
    private int reorderThreshold;

    protected InventoryItem() {
        // JPA cần constructor không tham số public/protected.
    }

    public InventoryItem(Integer quantity, int reorderThreshold) {
        if (quantity == null || quantity < 0 || reorderThreshold < 0) {
            throw new IllegalArgumentException("Số lượng không hợp lệ");
        }
        this.quantity = quantity;
        this.reorderThreshold = reorderThreshold;
    }

    public Long getId() {
        return id;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void receive(int added) {
        if (added <= 0) {
            throw new IllegalArgumentException("Số lượng nhập phải dương");
        }
        this.quantity = Math.addExact(this.quantity, added);
    }
}
```

Với nhiều database, provider sẽ ánh xạ `id` thành kiểu `BIGINT` hoặc kiểu định danh tương ứng, còn `quantity` và `reorderThreshold` thường thành `INTEGER`. `@Column(precision = ..., scale = ...)` **không phải công cụ chính để quy định số bit của cột nguyên**; với số nguyên cố định, chọn kiểu Java đúng, dùng `@Column` cho tên/nullability và tùy tình huống chỉ định kiểu SQL một cách có kiểm soát.

Phương thức `Math.addExact` phát hiện tràn số `int` khi cộng thay vì âm thầm quay vòng giá trị. Nếu nghiệp vụ có thể chứa số lượng lớn hơn `int`, nên chuyển sang `Long` hoặc kiểu phù hợp ngay từ thiết kế.

## 3. Hai nhóm số thập phân: chính xác và gần đúng

Đây là phân biệt quan trọng nhất trước khi nói đến `precision` và `scale`.

### 3.1. `BigDecimal` cho số thập phân chính xác

`java.math.BigDecimal` lưu một giá trị thập phân theo dạng **số nguyên không giới hạn về độ lớn về mặt mô hình kết hợp với scale**, cho phép biểu diễn chính xác các giá trị như `0.1`, `12.50` và `1999999.99` nếu khởi tạo đúng.

```java
BigDecimal price = new BigDecimal("125000.50");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = price.multiply(taxRate);
```

`BigDecimal` phù hợp với:

- Giá bán, chiết khấu, số tiền thanh toán, công nợ.
- Tỷ giá, tỷ lệ thuế và đại lượng phải tuân theo quy tắc làm tròn xác định.
- Số đo mà việc lưu đúng chữ số thập phân là một yêu cầu nghiệp vụ.

JPA thường ánh xạ `BigDecimal` sang SQL `DECIMAL` hoặc `NUMERIC`, là các kiểu **exact numeric**. Từ đây, `@Column(precision = p, scale = s)` mang ý nghĩa rõ ràng với thiết kế cột.

### 3.2. `float` và `double` cho số gần đúng

`float` / `Float` và `double` / `Double` lưu số ở dạng **dấu phẩy động nhị phân**. Nhiều giá trị thập phân đơn giản như `0.1` không được biểu diễn chính xác tuyệt đối bằng nhị phân.

```java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // Thường in 0.30000000000000004
```

Các kiểu này có ích cho phép đo khoa học, mô phỏng, tọa độ hoặc tính toán chấp nhận sai số. Chúng thường được ánh xạ sang SQL `REAL`, `FLOAT` hoặc `DOUBLE PRECISION` tùy database.

**Không dùng `double` hoặc `float` chỉ vì muốn “được nhiều số sau dấu phẩy” khi lưu tiền.** `@Column(precision = 15, scale = 2)` mô tả cấu trúc cột **decimal chính xác**; annotation này không biến dữ liệu nhị phân `double` thành phép tính tiền chính xác.

| Mục tiêu | Kiểu Java thường phù hợp | Kiểu SQL gợi ý |
|---|---|---|
| Số lượng nguyên | `Integer` hoặc `Long` | `INTEGER` / `BIGINT` |
| Số nguyên rất lớn | `BigInteger` | `NUMERIC(p, 0)`, cân nhắc giới hạn |
| Giá tiền với 2 chữ số thập phân | `BigDecimal` | `DECIMAL(p, 2)` |
| Tỷ lệ phần trăm có độ phân giải cố định | `BigDecimal` | `DECIMAL(p, s)` |
| Phép đo chấp nhận sai số gần đúng | `Double` | `DOUBLE PRECISION` hoặc tương đương |

## 4. `precision` và `scale` là gì?

### 4.1. Ý nghĩa của `DECIMAL(p, s)`

Đối với cột thập phân chính xác:

- **Precision (`p`)** là **tổng số chữ số thập phân** mà kiểu cột được thiết kế để lưu, tính cả bên trái và bên phải dấu thập phân; không tính dấu âm và dấu chấm.
- **Scale (`s`)** là **số chữ số ở phần thập phân**, tức phía bên phải dấu thập phân.
- Trong mô hình SQL `DECIMAL(p, s)` thường dùng, phần nguyên có thể có tối đa **`p - s` chữ số**.

Ví dụ:

```text
DECIMAL(8, 2)
        |  |
        |  +-- scale = 2 chữ số sau dấu thập phân
        +----- precision = 8 chữ số tổng cộng

        123456.78
        |----| ||
          6     2

p - s = 8 - 2 = 6 chữ số phần nguyên
```

Với `DECIMAL(8, 2)`, các giá trị phù hợp thường nằm trong khoảng **-999999.99 đến 999999.99**, tăng theo bước **0.01** nếu giá trị đã được chuẩn hóa về hai chữ số thập phân. Cách xử lý khi ứng dụng gửi nhiều chữ số thập phân hơn phụ thuộc database, chế độ SQL và driver: có hệ thống làm tròn theo quy tắc của nó, có hệ thống báo lỗi; không nên dựa vào một hành vi chung.

### 4.2. Ví dụ tính giới hạn

| Cấu hình cột | Tổng chữ số (`p`) | Chữ số lẻ (`s`) | Tối đa chữ số phần nguyên | Giá trị dương lớn nhất theo phạm vi thường gặp |
|---|---:|---:|---:|---:|
| `DECIMAL(5, 0)` | 5 | 0 | 5 | `99999` |
| `DECIMAL(7, 2)` | 7 | 2 | 5 | `99999.99` |
| `DECIMAL(10, 2)` | 10 | 2 | 8 | `99999999.99` |
| `DECIMAL(15, 2)` | 15 | 2 | 13 | `9999999999999.99` |
| `DECIMAL(18, 6)` | 18 | 6 | 12 | `999999999999.999999` |
| `DECIMAL(19, 4)` | 19 | 4 | 15 | `999999999999999.9999` |

Đối với các dạng cột phổ biến, ta thường chọn **`p >= s >= 0`**. Một số RDBMS hỗ trợ mở rộng như negative scale hoặc giới hạn precision đặc thù; khi cần tính di động, nên dựa trên cấu hình `DECIMAL(p, s)` được cả hệ quản trị mục tiêu hỗ trợ.

Công thức kiểm tra nhanh:

```text
Số chữ số phần nguyên tối đa = precision - scale

Ví dụ:
DECIMAL(15, 2) -> 13 chữ số nguyên + 2 chữ số lẻ
DECIMAL(12, 4) ->  8 chữ số nguyên + 4 chữ số lẻ
DECIMAL(9,  0) ->  9 chữ số nguyên + 0 chữ số lẻ
```

**Precision không phải “số chữ số trước dấu phẩy”.** Nhầm lẫn này dễ khiến chọn cột quá nhỏ. Nếu cần **12 chữ số phần nguyên và 4 chữ số lẻ**, chọn precision ít nhất **16**, tức `DECIMAL(16, 4)`, chứ không phải `DECIMAL(12, 4)`.

### 4.3. Giá trị âm, số 0 và số dư thập phân

Dấu âm không tính vào precision. Với `DECIMAL(5, 2)`, `-123.45` sử dụng 5 chữ số và phù hợp với phạm vi thông thường.

Số 0 hoặc số nhỏ hơn 1 vẫn là giá trị có thể lưu vào cột decimal. Ví dụ `0.05` được lưu chính xác với scale 2; việc hiển thị `0.05` hay `0.050` trong Java phụ thuộc `BigDecimal` và cách định dạng, còn database có quy tắc lưu/đọc riêng với cột scale cố định.

Điều quan trọng là **độ chính xác và scale của cột SQL không phải thuộc tính tự động áp lên mọi đối tượng `BigDecimal` đang sống trong bộ nhớ Java**. Một `BigDecimal("1.2345")` vẫn có scale 4 ngay sau khi tạo, bất kể sau này ứng dụng sẽ ghi nó vào `DECIMAL(10, 2)`.

## 5. Ánh xạ `precision` và `scale` bằng `@Column`

Trong JPA, `@Column` cung cấp các thuộc tính:

```java
@Column(
    name = "unit_price",
    nullable = false,
    precision = 15,
    scale = 2
)
private BigDecimal unitPrice;
```

Ý nghĩa:

- `name`: tên cột SQL.
- `nullable`: cột có được phép nhận SQL `NULL` khi sinh schema hay không.
- `precision`: số chữ số tổng cho cột decimal/exact numeric.
- `scale`: số chữ số thập phân cho cột decimal/exact numeric.

Nếu provider dùng đúng metadata trên để tạo schema, một kết quả phổ biến là:

```sql
unit_price DECIMAL(15, 2) NOT NULL
```

Tên kiểu SQL thực tế, cách khai báo ràng buộc và việc cập nhật một bảng **đã tồn tại** phụ thuộc JPA provider, SQL dialect và chiến lược schema management. `@Column` là metadata ánh xạ; **không phải một công cụ migration schema tự động được bảo đảm**.

Khi `precision` / `scale` không được chỉ định, JPA/provider áp dụng mặc định hoặc suy luận kiểu SQL phù hợp. Không nên giả định mặc định luôn là `DECIMAL(19,2)` hoặc một giá trị cố định áp dụng cho mọi provider.

### 5.1. Ví dụ entity có nhiều kiểu số

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "stock_quantity", nullable = false)
    private Integer stockQuantity;

    @Column(name = "unit_price", nullable = false,
            precision = 15, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "weight_kg",
            precision = 12, scale = 3)
    private BigDecimal weightKg;

    @Column(name = "discount_rate", nullable = false,
            precision = 7, scale = 6)
    private BigDecimal discountRate;

    protected Product() {
        // Constructor không tham số cho JPA.
    }

    public Product(Integer stockQuantity,
                   BigDecimal unitPrice,
                   BigDecimal weightKg,
                   BigDecimal discountRate) {
        if (stockQuantity == null || stockQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không hợp lệ");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không hợp lệ");
        }
        if (discountRate == null ||
                discountRate.compareTo(BigDecimal.ZERO) < 0 ||
                discountRate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "Tỷ lệ giảm giá phải nằm trong [0, 1]");
        }
        if (weightKg != null && weightKg.signum() < 0) {
            throw new IllegalArgumentException("Khối lượng không hợp lệ");
        }

        this.stockQuantity = stockQuantity;
        this.unitPrice = unitPrice.setScale(2);
        this.weightKg = weightKg == null
                ? null
                : weightKg.setScale(3);
        this.discountRate = discountRate.setScale(6);
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal getDiscountRate() {
        return discountRate;
    }

    public BigDecimal discountedPrice() {
        return unitPrice
                .multiply(BigDecimal.ONE.subtract(discountRate))
                .setScale(2, java.math.RoundingMode.HALF_EVEN);
    }
}
```

Các giá trị được đưa vào constructor của ví dụ này cần có scale phù hợp khi dùng `setScale(2)`, `setScale(3)` và `setScale(6)` **không chỉ định rounding mode**. Nếu phép chuẩn hóa phải bỏ chữ số có nghĩa, Java sẽ ném `ArithmeticException` thay vì âm thầm làm tròn. Cách này có thể được dùng để từ chối input không đúng đơn vị đo; nếu nghiệp vụ cho phép làm tròn, ứng dụng phải quy định rõ `RoundingMode`.

Các cột dữ liệu tương ứng thường là:

| Thuộc tính entity | Kiểu Java | Cột SQL dự kiến | Ý nghĩa |
|---|---|---|---|
| `id` | `Long` | `BIGINT` / loại identity phù hợp | Khóa định danh tự sinh |
| `stockQuantity` | `Integer` | `INTEGER NOT NULL` | Số lượng nguyên |
| `unitPrice` | `BigDecimal` | `DECIMAL(15,2) NOT NULL` | Giá với 2 chữ số thập phân |
| `weightKg` | `BigDecimal` | `DECIMAL(12,3)` | Khối lượng với 3 chữ số thập phân |
| `discountRate` | `BigDecimal` | `DECIMAL(7,6) NOT NULL` | Tỷ lệ từ 0 đến 1, độ phân giải 6 chữ số |

`DECIMAL(7,6)` có một chữ số phần nguyên, nên có thể chứa `1.000000` hoặc `0.125000`; tuy vậy, nó **không tự cấm** các giá trị không hợp lệ về nghiệp vụ như `2.000000` hoặc số âm. Constructor hoặc validation/database `CHECK` phải đảm nhiệm quy tắc từ 0 đến 1.

### 5.2. Sơ đồ từ field đến cột

```text
Entity Product
|
+-- Long id
|      -> BIGINT / identity
|
+-- Integer stockQuantity
|      -> INTEGER
|
+-- BigDecimal unitPrice
|      -> DECIMAL(15, 2)
|             p=15, s=2
|             tối đa 13 chữ số phần nguyên
|
+-- BigDecimal weightKg
|      -> DECIMAL(12, 3)
|             p=12, s=3
|             tối đa 9 chữ số phần nguyên
|
+-- BigDecimal discountRate
       -> DECIMAL(7, 6)
              p=7, s=6
              tối đa 1 chữ số phần nguyên
```

Một DDL minh họa bằng SQL, **không phải cam kết output của mọi provider**, có thể là:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    stock_quantity INTEGER NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL,
    weight_kg DECIMAL(12, 3),
    discount_rate DECIMAL(7, 6) NOT NULL
);
```

Cú pháp identity khác nhau giữa các hệ quản trị; khi cần chạy DDL thực tế, hãy dùng dialect hoặc script migration phù hợp với database mục tiêu.

## 6. Làm tròn và chuẩn hóa `BigDecimal`

### 6.1. Tạo `BigDecimal` đúng cách

**Nên dùng:**

```java
BigDecimal price = new BigDecimal("199.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal fee = BigDecimal.valueOf(0.1);
```

**Tránh dùng khi cần giá trị thập phân chính xác:**

```java
BigDecimal wrong = new BigDecimal(0.1);
```

`new BigDecimal(0.1)` chuyển chính xác giá trị nhị phân của `double` vào decimal, có thể chứa chuỗi chữ số dài không mong muốn. `new BigDecimal("0.1")` biểu diễn giá trị thập phân 0.1 chính xác; `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi decimal thông dụng của `double` nên thường phù hợp hơn khi bắt đầu từ một giá trị số gần đúng đã có.

### 6.2. `scale` của BigDecimal và scale của cột

`BigDecimal` có phương thức `scale()`:

```java
BigDecimal a = new BigDecimal("12.3");
BigDecimal b = new BigDecimal("12.30");

System.out.println(a.scale()); // 1
System.out.println(b.scale()); // 2
```

Hai object có cùng giá trị toán học nhưng scale khác nhau. `@Column(scale = 2)` chỉ định yêu cầu ánh xạ cột decimal; **không bảo đảm mọi giá trị `BigDecimal` Java tự có `scale() == 2`** sau khi đọc hoặc trước khi lưu ở mọi provider/database.

Khi nghiệp vụ muốn làm việc nhất quán với hai chữ số lẻ, chuẩn hóa có chủ đích:

```java
BigDecimal input = new BigDecimal("12.345");

BigDecimal rounded =
        input.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 12.35
```

Các chiến lược `RoundingMode` phổ biến:

| Chiến lược | Hành vi (khi cần bỏ chữ số) | Khi cân nhắc sử dụng |
|---|---|---|
| `UNNECESSARY` | Không cho phép làm tròn; nếu cần sẽ ném `ArithmeticException`. | Từ chối dữ liệu không đúng số lẻ yêu cầu. |
| `HALF_UP` | Giá trị nằm đúng giữa hai mức được làm tròn theo hướng xa 0. | Một số quy tắc tính tiền/thuế quy định cụ thể. |
| `HALF_EVEN` | Giá trị ở đúng giữa được làm tròn về chữ số chẵn gần nhất. | Tính toán lặp lại và quy tắc giảm sai lệch tích lũy. |
| `DOWN` | Bỏ phần vượt quá theo hướng về 0. | Tình huống cố ý cắt bỏ chữ số. |
| `UP` | Làm tròn ra xa 0 nếu còn phần bị bỏ. | Quy tắc đặc biệt yêu cầu luôn tăng độ lớn. |

Không có một `RoundingMode` đúng cho mọi nghiệp vụ. Cần dựa vào quy định kế toán, hợp đồng, chính sách thuế và ý nghĩa đại lượng; không mặc nhiên chọn `HALF_UP` cho mọi trường hợp.

### 6.3. Phép cộng, nhân và chia

Phép cộng và nhân `BigDecimal` thông thường giữ độ chính xác thập phân, nhưng kết quả có thể có scale lớn hơn dữ liệu đích:

```java
BigDecimal unitPrice = new BigDecimal("19.95");
BigDecimal quantity = BigDecimal.valueOf(3);
BigDecimal total = unitPrice.multiply(quantity);

System.out.println(total); // 59.85
```

Khi nhân với tỷ lệ:

```java
BigDecimal rate = new BigDecimal("0.075");
BigDecimal tax = total.multiply(rate);

System.out.println(tax); // 4.48875
```

Nếu `tax` cần lưu vào `DECIMAL(15,2)`, hãy làm tròn theo quy tắc nghiệp vụ **trước khi lưu**:

```java
BigDecimal taxForStorage =
        tax.setScale(2, RoundingMode.HALF_EVEN);
```

Khi chia không ra kết quả thập phân hữu hạn, cần chỉ rõ scale và rounding mode (hoặc một `MathContext` thích hợp):

```java
BigDecimal average = new BigDecimal("10")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);

System.out.println(average); // 3.33
```

`new BigDecimal("10").divide(new BigDecimal("3"))` không chỉ định cách xử lý kết quả vô hạn có thể ném `ArithmeticException`.

### 6.4. `equals()` và `compareTo()`

`BigDecimal.equals()` so sánh cả giá trị lẫn scale:

```java
BigDecimal x = new BigDecimal("10.0");
BigDecimal y = new BigDecimal("10.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

Khi so sánh giá trị tiền hoặc tỷ lệ về mặt toán học trong mã nghiệp vụ, dùng `compareTo()` là lựa chọn phổ biến. Khi muốn so khớp chặt chẽ cả cách biểu diễn và scale, `equals()` có ý nghĩa khác. Lưu ý hệ quả khi dùng `BigDecimal` làm khóa trong các cấu trúc dựa vào `equals/hashCode`.

## 7. Precision và scale không thay thế validation

### 7.1. Ba lớp bảo vệ dữ liệu

Một thuộc tính giá có thể được bảo vệ tại ba mức:

1. **Logic nghiệp vụ Java:** từ chối giá âm, chuẩn hóa số chữ số lẻ, giới hạn giá trị khi khởi tạo/thay đổi entity.
2. **Jakarta Bean Validation:** kiểm tra các constraint như `@NotNull`, `@PositiveOrZero` và `@Digits` khi framework/validation integration được kích hoạt.
3. **Cơ sở dữ liệu:** cột `DECIMAL(p,s)`, `NOT NULL`, `CHECK` và các ràng buộc khác bảo vệ dữ liệu được ghi từ mọi client.

Chẳng hạn Bean Validation:

```java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;

@NotNull
@DecimalMin("0.00")
@Digits(integer = 13, fraction = 2)
@Column(nullable = false, precision = 15, scale = 2)
private BigDecimal unitPrice;
```

Ở đây:

- `@Digits(integer = 13, fraction = 2)` kiểm tra tối đa **13 chữ số nguyên** và **2 chữ số lẻ**; tương ứng ý định của `DECIMAL(15,2)`.
- `@DecimalMin("0.00")` loại giá âm.
- `@NotNull` yêu cầu input không null ở tầng validation.
- `@Column(nullable = false, precision = 15, scale = 2)` mô tả column mapping và DDL kỳ vọng.

Để các annotation trong gói `jakarta.validation` được thực thi, project cần Bean Validation API và implementation, đồng thời tích hợp validation phù hợp. Annotation validation tự nó không có nghĩa mọi setter đều lập tức chạy kiểm tra; thời điểm validate phụ thuộc luồng ứng dụng và framework.

**Đừng nhầm hai cách đếm:** `@Digits(integer=13, fraction=2)` lấy phần nguyên/lẻ riêng; `@Column(precision=15, scale=2)` định nghĩa **tổng 15 chữ số**, trong đó 2 chữ số lẻ.

### 7.2. Nếu dữ liệu vượt precision/scale thì sao?

Giả sử cột là `DECIMAL(6,2)`:

| Input | Nhận xét |
|---|---|
| `1234.56` | 4 chữ số nguyên + 2 chữ số lẻ, phù hợp. |
| `9999.99` | Đạt biên dương của phạm vi thông thường. |
| `10000.00` | Cần 5 chữ số nguyên, vượt giới hạn 4. |
| `12.345` | Có 3 chữ số lẻ, vượt scale 2. |
| `-1.20` | Dấu âm không tính vào precision; phù hợp. |

Với giá trị vượt **phạm vi phần nguyên**, database thường từ chối hoặc báo lỗi phạm vi số. Với giá trị có nhiều chữ số lẻ, một số database **làm tròn**, một số lỗi hoặc chịu cấu hình nghiêm ngặt của hệ thống. Không nên dựa vào việc driver/database tự xử lý vì sẽ khó kiểm soát kết quả tài chính.

Ở Java, kiểm tra trước khi ghi giúp thông báo lỗi rõ ràng hơn. Ví dụ:

```java
public static BigDecimal normalizeMoney(BigDecimal value) {
    if (value == null || value.signum() < 0) {
        throw new IllegalArgumentException("Số tiền không hợp lệ");
    }

    BigDecimal normalized =
            value.setScale(2, RoundingMode.UNNECESSARY);

    if (normalized.precision() > 15) {
        throw new IllegalArgumentException(
                "Số tiền vượt quá phạm vi DECIMAL(15,2)");
    }

    return normalized;
}
```

`setScale(2, UNNECESSARY)` ở đây chủ động từ chối giá trị phải làm tròn; `precision()` sau khi chuẩn hóa là cách kiểm tra phạm vi chữ số đối với giá trị decimal thông thường. Khi xây dựng hệ thống thật, cần bổ sung test biên, xử lý kiểu dữ liệu, quy tắc số âm và các trường hợp đặc biệt đúng với domain.

## 8. `@Column(columnDefinition)` và tính di động

Có thể yêu cầu kiểu SQL cụ thể:

```java
@Column(
    name = "amount",
    columnDefinition = "NUMERIC(19,4)"
)
private BigDecimal amount;
```

Khác biệt:

- `precision` / `scale` mô tả thuộc tính số theo **metadata chuẩn JPA**, tạo điều kiện cho dialect sinh SQL phù hợp từng database.
- `columnDefinition` đặt chuỗi SQL dùng cho cột khi provider tạo DDL. Chuỗi này có thể phụ thuộc database và giảm tính di động, thậm chí có thể mâu thuẫn với các metadata khác.

Nên **ưu tiên `precision` / `scale`** nếu chỉ cần một cột decimal chính xác. Dùng `columnDefinition` khi có lý do kỹ thuật rõ ràng, chẳng hạn muốn một SQL type đặc biệt của database mà JPA metadata thông thường không biểu diễn đúng. Nếu database không hỗ trợ đúng kiểu SQL đó, quá trình tạo schema sẽ lỗi.

`@Column(length = ...)` chủ yếu áp dụng cho cột kiểu chuỗi/nhị phân theo đặc tả, **không dùng để giới hạn số chữ số decimal**. Khi cần giới hạn độ lớn số, chọn precision, scale và validation thích hợp.

## 9. Kiểu `BigInteger` và số nguyên vượt 64 bit

`BigInteger` chứa số nguyên có độ lớn tùy ý về mặt Java, rất hữu ích khi giá trị vượt `Long.MAX_VALUE`:

```java
import java.math.BigInteger;

BigInteger value =
        new BigInteger("123456789012345678901234567890");
```

Trong entity có thể khai báo:

```java
@Column(name = "external_counter", precision = 30, scale = 0)
private BigInteger externalCounter;
```

Ý định ở đây là cột `NUMERIC(30,0)` hoặc tương đương. Cần nhớ:

- `BigInteger` không có phần thập phân; `scale = 0` thể hiện ý định lưu số nguyên chính xác.
- Provider/dialect phải hỗ trợ ánh xạ `BigInteger` sang SQL numeric phù hợp; kiểm tra schema thực tế.
- `BigInteger` có thể rất lớn trong Java, còn cột SQL bị giới hạn bởi `precision` và giới hạn tối đa của database.
- Nếu dữ liệu chỉ cần phạm vi 64 bit, `Long` và `BIGINT` thường đơn giản hơn.

Cẩn thận khi chuyển đổi:

```java
BigInteger huge = new BigInteger("12345678901234567890");

// Kiểm tra tràn phạm vi; ném ArithmeticException nếu không vừa:
long result = huge.longValueExact();
```

Các phương thức như `longValue()` hoặc `intValue()` có thể **bỏ phần bit cao**, làm mất dữ liệu. Khi chuyển một `BigDecimal` về số nguyên, dùng `toBigIntegerExact()` hoặc `longValueExact()` nếu cần từ chối mọi phần lẻ/tràn phạm vi.

## 10. Thực hành lưu và truy vấn thuộc tính số

### 10.1. Lưu số nguyên và BigDecimal bằng resource-local transaction

Giả sử đã có `EntityManagerFactory emf` được tạo từ persistence unit `RESOURCE_LOCAL` và entity `Product` ở phần 5 đã được đăng ký:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Product product = new Product(
                25,
                new BigDecimal("1299000.00"),
                new BigDecimal("1.250"),
                new BigDecimal("0.075000")
        );

        em.persist(product);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Các giá trị có ý nghĩa:

- Tồn kho **25**: `Integer`, dự kiến lưu trong `INTEGER`.
- Đơn giá **1.299.000,00**: `BigDecimal`, dự kiến lưu trong `DECIMAL(15,2)`.
- Khối lượng **1,250 kg**: `BigDecimal`, dự kiến lưu trong `DECIMAL(12,3)`.
- Giảm giá **0,075000 = 7,5%**: `BigDecimal`, dự kiến lưu trong `DECIMAL(7,6)`.

Không tạo tiền bằng số thực nhị phân rồi truyền thẳng vào constructor khi cần số tiền chính xác. `new BigDecimal("1299000.00")` thể hiện giá trị thập phân rõ ràng.

### 10.2. JPQL và tham số kiểu `BigDecimal`

Truy vấn các sản phẩm có giá ít nhất 100.000:

```java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p WHERE p.unitPrice >= :minimum",
        Product.class
    )
    .setParameter("minimum", new BigDecimal("100000.00"))
    .getResultList();
```

JPQL dùng **tên thuộc tính entity** `unitPrice`, không dùng tên cột SQL `unit_price`. Provider chịu trách nhiệm tạo SQL và bind tham số sang kiểu JDBC phù hợp.

Tránh nối chuỗi để xây numeric literal đầu vào:

```java
// Không nên:
String jpql = "SELECT p FROM Product p WHERE p.unitPrice >= "
        + userInput;
```

Dùng parameter binding để giữ kiểu dữ liệu, tránh lỗi cú pháp/lệ thuộc locale và hạn chế nguy cơ injection.

### 10.3. Phép tổng hợp trên kiểu số

JPA hỗ trợ aggregate như `SUM`, `AVG` và `COUNT`. Ví dụ:

```java
BigDecimal totalPrice = em.createQuery(
        "SELECT SUM(p.unitPrice) FROM Product p",
        BigDecimal.class
).getSingleResult();
```

Theo quy tắc JPQL, `SUM` trên thuộc tính `BigDecimal` trả về `BigDecimal`; `SUM` trên thuộc tính nguyên thường dùng `Long`; `COUNT` trả về `Long`. Trong tập dữ liệu trống hoặc khi mọi giá trị đều null, các aggregate khác `COUNT` có thể trả về `null`. Hãy xét kỹ nghiệp vụ trước khi cộng/tính trung bình; aggregate này cộng **giá niêm yết theo hàng**, chưa nhân với số lượng, nên không tự trở thành tổng giá trị tồn kho.

Một số biểu thức tính toán trong SQL/JPQL có thể khiến database tính độ chính xác và scale cho **kết quả trung gian** theo quy tắc riêng. Đặc biệt khi nhân/chia nhiều cột `DECIMAL`, cần kiểm tra kiểu và độ chính xác của expression, tránh mặc nhiên cho rằng đầu ra vẫn có đúng scale của một cột nguồn.

## 11. Thay đổi precision/scale trên database đang chạy

Giả sử bảng `products` hiện có:

```sql
unit_price DECIMAL(10, 2)
```

Sau một thời gian, nghiệp vụ cần tăng khả năng lưu giá lớn và muốn chuyển sang `DECIMAL(15, 2)`.

Chỉ sửa entity từ:

```java
@Column(precision = 10, scale = 2)
private BigDecimal unitPrice;
```

thành:

```java
@Column(precision = 15, scale = 2)
private BigDecimal unitPrice;
```

**không bảo đảm cột thật trong database được thay đổi** khi ứng dụng khởi động. Việc tạo hoặc cập nhật schema phụ thuộc chế độ schema management của provider và database; với môi trường production nên dùng migration có kiểm soát như Flyway, Liquibase hoặc script SQL được kiểm duyệt.

Khi đổi schema:

1. **Tăng precision, giữ scale:** thường là mở rộng phạm vi phần nguyên, nhưng vẫn cần kiểm tra loại cột/dialect và tác động về lưu trữ.
2. **Giảm precision:** có thể làm giá trị cũ không còn vừa cột.
3. **Giảm scale:** có nguy cơ làm tròn, mất dữ liệu thập phân hoặc lỗi chuyển đổi.
4. **Tăng scale mà giữ precision:** làm **giảm số chữ số phần nguyên**; chẳng hạn `DECIMAL(10,2)` có 8 chữ số phần nguyên nhưng `DECIMAL(10,4)` chỉ còn 6.
5. **Thay đổi kiểu integer thành decimal hoặc ngược lại:** xem lại phạm vi, conversion, query, index, validation và code Java tương ứng.

Một quy trình migration thực tế cần kiểm tra dữ liệu hiện có, xác định cách xử lý giá trị vượt giới hạn, thử trên bản sao dữ liệu và triển khai theo kế hoạch của hệ thống. Không dùng `drop-and-create` trên database cần giữ dữ liệu.

## 12. Những lỗi phổ biến và cách tránh

| Tình huống | Nguyên nhân / hướng xử lý |
|---|---|
| Khai báo `BigDecimal` nhưng quên precision/scale cho giá tiền | Provider chọn mặc định khó dự đoán; khai báo rõ `@Column(precision = ..., scale = ...)` theo phạm vi nghiệp vụ. |
| Hiểu `precision = 12` là 12 chữ số phần nguyên khi `scale = 2` | Phần nguyên tối đa thường chỉ có `12 - 2 = 10` chữ số. |
| Dùng `double` để lưu tiền | Dấu phẩy động nhị phân không biểu diễn chính xác mọi phân số thập phân; dùng `BigDecimal`. |
| Dùng `new BigDecimal(0.1)` | Chuyển giá trị binary float thành decimal dài; dùng chuỗi hoặc `BigDecimal.valueOf`. |
| Gọi `setScale(2)` với giá trị có nhiều hơn hai chữ số có nghĩa | Nếu cần làm tròn mà không chỉ định cách, Java ném `ArithmeticException`; chọn chính sách làm tròn hoặc từ chối input. |
| Cứ `flush()` là đã lưu thành công | Flush không thay commit; transaction có thể rollback hoặc commit lỗi. |
| Giá trị vượt phạm vi nhưng chỉ trông đợi database tự xử lý | Kiểm tra biên ở tầng nghiệp vụ/validation và giữ constraint DB, làm rõ trường hợp làm tròn hay từ chối. |
| Dùng `@Column(length = 20)` để tăng số chữ số | `length` không điều khiển precision của cột numeric; dùng `precision`, `scale`. |
| Chỉ đổi annotation rồi mong schema production tự đổi | Dùng migration và kiểm tra dữ liệu cũ; annotation không thay thế schema migration. |
| Dùng `BigDecimal.equals()` để so sánh tiền | `10.0` và `10.00` khác scale nên `equals()` trả `false`; dùng `compareTo()` nếu so giá trị toán học. |
| Dùng `Integer` cho bộ đếm có thể vượt khoảng 2,1 tỷ | Kiểu Java/cột SQL không đủ phạm vi; chọn `Long` hoặc kiểu thích hợp. |
| Dùng `precision/scale` cho `Double` rồi kỳ vọng tính toán decimal chính xác | Thuộc tính này nhắm tới cột decimal exact numeric; dùng `BigDecimal` nếu cần số thập phân chính xác. |
| Dùng `DECIMAL(7,6)` để giới hạn tỷ lệ trong [0,1] | Định nghĩa decimal không tự áp constraint miền giá trị; thêm validation hoặc `CHECK` của database. |
| Dùng giá trị BigDecimal từ API mà không biết đơn vị | Dữ liệu có thể là phần trăm 7.5 thay vì tỷ lệ 0.075; xác định đơn vị/scale từ hợp đồng dữ liệu trước khi lưu. |

## 13. Cách chọn `precision` và `scale` theo nghiệp vụ

Một quy trình thiết kế hữu ích:

**Bước 1: Xác định đại lượng.** Đây là số lượng nguyên, mã định danh, tiền, khối lượng hay tỷ lệ? Nếu là số nguyên, ưu tiên kiểu nguyên; nếu cần biểu diễn decimal chính xác, ưu tiên `BigDecimal`.

**Bước 2: Xác định giá trị lớn nhất cần hỗ trợ.** Ví dụ giá sản phẩm lớn nhất dự kiến không quá `9.999.999.999,99`, tương ứng tối đa **10 chữ số phần nguyên**.

**Bước 3: Chọn số chữ số lẻ theo đơn vị và quy tắc làm tròn.** Ví dụ tiền có 2 chữ số lẻ, khối lượng có 3 chữ số lẻ, tỷ lệ cần 6 chữ số lẻ. Không suy luận mặc định mọi tiền tệ đều có hai đơn vị thập phân; một số đơn vị tiền tệ và hệ thống hạch toán có yêu cầu khác.

**Bước 4: Tính precision.** Lấy số chữ số phần nguyên tối đa cộng scale:

```text
max integer digits = 10
scale              = 2
precision          = 10 + 2 = 12

=> DECIMAL(12, 2)
=> @Column(precision = 12, scale = 2)
```

**Bước 5: Ràng buộc dữ liệu ở đúng tầng.** Dùng validation/domain rules để kiểm soát giá trị, scale đầu vào và rounding; dùng database constraint để bảo vệ dữ liệu độc lập với ứng dụng.

**Bước 6: Kiểm tra dialect/schema thực tế.** Xem DDL được tạo hoặc migration đã áp dụng, kiểm tra giới hạn của RDBMS và chạy các ca thử biên phù hợp trong giai đoạn triển khai/QA. Việc xác minh schema là bước vận hành dự án thực tế, không thể thay bằng chỉ nhìn annotation.

### Ví dụ lựa chọn

| Đại lượng | Giá trị mẫu | Kiểu Java đề xuất | Cột SQL đề xuất |
|---|---|---|---|
| Số lượng trong kho | `1200` | `Integer` | `INTEGER` |
| Lượt truy cập tích lũy lớn | `8500000000` | `Long` | `BIGINT` |
| Giá bán có 2 chữ số lẻ | `1299000.50` | `BigDecimal` | `DECIMAL(15,2)` |
| Khối lượng chính xác đến 0,001 kg | `1.235` | `BigDecimal` | `DECIMAL(12,3)` |
| Tỷ lệ giảm giá từ 0 đến 1, sáu chữ số lẻ | `0.075000` | `BigDecimal` | `DECIMAL(7,6)` |
| Số nguyên vượt 64 bit | `123456789012345678901234567890` | `BigInteger` | `NUMERIC(30,0)` hoặc cột lớn hơn nếu cần |

## 14. Câu hỏi tự kiểm tra

**1. Với `DECIMAL(12, 3)`, có tối đa bao nhiêu chữ số phần nguyên?**

Có **9 chữ số**: `12 - 3 = 9`. Tổng precision là 12, trong đó 3 chữ số thuộc phần thập phân.

**2. `@Column(precision = 10, scale = 2)` có tự làm tròn đối tượng `BigDecimal` Java về hai chữ số lẻ?**

Không. Annotation là metadata ánh xạ cột; ứng dụng nên chuẩn hóa hoặc validate giá trị trước khi lưu. Cách database xử lý số lẻ vượt scale phụ thuộc cấu hình và RDBMS.

**3. Vì sao không nên dùng `Double` cho giá tiền?**

Vì giá trị nhị phân gần đúng có thể gây sai số biểu diễn/tính toán với số thập phân. `BigDecimal` kết hợp decimal SQL, quy tắc rounding rõ ràng phù hợp hơn.

**4. Có thể lưu `10000.00` trong `DECIMAL(6,2)` không?**

Không theo phạm vi decimal thường gặp: cột chỉ cho phép tối đa **4 chữ số phần nguyên**, trong khi `10000` có 5 chữ số.

**5. `@Digits(integer=13, fraction=2)` và `@Column(precision=15, scale=2)` có giống nhau không?**

Chúng diễn đạt giới hạn tương ứng về chữ số nhưng ở **hai tầng khác nhau**. `@Digits` là validation constraint nếu được tích hợp và chạy; `@Column` là metadata cho việc ánh xạ cột SQL.

**6. Có nên dùng `BigInteger` cho mọi số nguyên để “không bao giờ tràn”?**

Không nhất thiết. `BigInteger` trong Java có phạm vi rất lớn nhưng cột DB vẫn có giới hạn; kiểu `Integer` hoặc `Long` thường dễ dùng, lưu trữ hiệu quả và phù hợp hơn nếu phạm vi nghiệp vụ cho phép.

**7. Nếu cần lưu 12 chữ số nguyên và 4 chữ số lẻ thì chọn cấu hình gì?**

Chọn ít nhất `DECIMAL(16,4)`, tương ứng `@Column(precision=16, scale=4)`.

**8. Khi cập nhật `@Column(precision=...)`, dữ liệu hiện có có tự chuyển không?**

Không có bảo đảm chung. Cần kiểm tra cấu hình tạo/cập nhật schema của provider và sử dụng migration phù hợp với database thực tế.

## 15. Tổng kết

Để ánh xạ số trong JPA đúng nhu cầu:

1. Chọn **`Integer`/`Long`** cho số nguyên trong phạm vi phù hợp, **`BigInteger`** cho số nguyên rất lớn, **`BigDecimal`** cho thập phân cần độ chính xác tuyệt đối theo hệ thập phân và **`Float`/`Double`** cho đại lượng chấp nhận sai số nhị phân.
2. Với SQL `DECIMAL(p,s)`, nhớ **`precision = tổng chữ số`**, **`scale = chữ số phần thập phân`**, và **`phần nguyên tối đa = p - s`**.
3. Khai báo **`@Column(precision, scale)`** trên thuộc tính exact decimal như `BigDecimal` để mô tả rõ ý định schema.
4. Xử lý **quy tắc làm tròn, validation, miền giá trị và transaction** ở tầng phù hợp; metadata ánh xạ không thay thế business rules hay constraints của database.
5. Kiểm tra cấu trúc cột do provider và dialect thực sự sử dụng, nhất là khi dữ liệu cần tính di động giữa RDBMS hoặc khi schema đã tồn tại.

Nắm rõ mối quan hệ **kiểu Java ↔ JDBC/provider ↔ kiểu SQL**, cùng cách tính `precision` và `scale`, giúp tránh những lỗi số học khó phát hiện trong ứng dụng JPA — đặc biệt ở dữ liệu tài chính và dữ liệu cần độ chính xác cao.
