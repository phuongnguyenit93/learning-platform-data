# Đánh giá tương thích khi quy tắc chuyển đổi thay đổi

Khi dùng JPA, một thuộc tính Java không nhất thiết được lưu xuống cơ sở dữ liệu đúng bằng hình dạng mà ta nhìn thấy trong mã nguồn. Một `Money` có thể được lưu thành số nguyên biểu diễn xu; một `OrderState` có thể được lưu bằng mã `"N"`; một `LocalDateTime` có thể cần quy ước múi giờ; một đối tượng giá trị có thể được chuyển thành JSON hoặc chuỗi có cấu trúc. Việc chuyển từ **giá trị trong mô hình Java** sang **giá trị trong cơ sở dữ liệu** và ngược lại được gọi là *quy tắc chuyển đổi*.

Trong JPA, quy tắc đó thường xuất hiện qua `AttributeConverter<X, Y>`, `@Convert`, cơ chế ánh xạ enum, kiểu JDBC, converter của provider hoặc logic biến đổi tại ranh giới ứng dụng. Khi quy tắc chuyển đổi thay đổi, ta phải đặt câu hỏi lớn hơn việc “code mới có biên dịch hay không”:

> **Dữ liệu được ghi bằng quy tắc cũ có còn được đọc, hiểu và cập nhật đúng bởi quy tắc mới không? Các phiên bản ứng dụng cũ và mới có thể cùng hoạt động mà không làm hỏng dữ liệu hay không?**

Đó là nội dung của bài học **“Đánh giá tương thích khi quy tắc chuyển đổi thay đổi”** trong chương **Kiểu giá trị** của chủ đề **Data Persistence, Relational Access, ORM và JPA**.

## 1. Quy tắc chuyển đổi là một hợp đồng dữ liệu

Giả sử hệ thống quản lý giao hàng có enum:

```java
public enum OrderState {
    NEW,
    SHIPPED,
    DELIVERED
}
```

Ở phiên bản đầu tiên, database lưu mã một ký tự:

| Giá trị Java | Giá trị cột `state_code` |
| --- | --- |
| `OrderState.NEW` | `"N"` |
| `OrderState.SHIPPED` | `"S"` |
| `OrderState.DELIVERED` | `"D"` |

Một converter JPA có thể diễn đạt hợp đồng ấy:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStateConverter
        implements AttributeConverter<OrderState, String> {

    @Override
    public String convertToDatabaseColumn(OrderState state) {
        if (state == null) return null;

        return switch (state) {
            case NEW       -> "N";
            case SHIPPED   -> "S";
            case DELIVERED -> "D";
        };
    }

    @Override
    public OrderState convertToEntityAttribute(String code) {
        if (code == null) return null;

        return switch (code) {
            case "N" -> OrderState.NEW;
            case "S" -> OrderState.SHIPPED;
            case "D" -> OrderState.DELIVERED;
            default -> throw new IllegalArgumentException(
                "Unknown order state code: " + code
            );
        };
    }
}
```

Entity áp dụng converter:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderStateConverter.class)
    @Column(name = "state_code", nullable = false, length = 1)
    private OrderState state;

    protected PurchaseOrder() {}

    public PurchaseOrder(OrderState initialState) {
        if (initialState == null) {
            throw new IllegalArgumentException("initialState");
        }
        this.state = initialState;
    }

    public OrderState getState() {
        return state;
    }
}
```

Ở đây, chính cột `state_code` chứa giá trị đã chuyển đổi, ví dụ `"S"`. Database không biết kiểu `OrderState` của Java. Khi code đọc bản ghi, converter phải biến chuỗi `"S"` thành `OrderState.SHIPPED`.

**Đặc điểm quan trọng:** quy tắc chuyển đổi trở thành một phần của *định dạng dữ liệu đã lưu*, tương tự cách đặt tên cột, kiểu dữ liệu hoặc định dạng JSON. Sửa converter có thể thay đổi khả năng đọc cả hàng triệu bản ghi cũ.

Trong entity, `protected PurchaseOrder()` phục vụ JPA, còn `PurchaseOrder(OrderState)` phục vụ tạo mới theo quy tắc nghiệp vụ. Getter `getState()` cho phép các ví dụ đọc trạng thái bên dưới sử dụng cùng một entity.

## 2. “Tương thích” gồm nhiều lớp khác nhau

Thay đổi converter không phải chỉ có hai trạng thái “tương thích” hoặc “không tương thích”. Ta phải đánh giá nhiều chiều:

| Lớp tương thích | Câu hỏi |
| --- | --- |
| **Kiểu Java/API** | Field, getter, setter và các lời gọi converter còn biên dịch và dùng đúng kiểu không? |
| **Định dạng dữ liệu** | Converter mới có đọc đúng giá trị được ghi bằng converter cũ không? |
| **Ý nghĩa nghiệp vụ** | Dữ liệu đọc được có giữ nguyên ý nghĩa, đơn vị, độ chính xác và ràng buộc không? |
| **Ghi/đọc hai chiều** | Giá trị do converter mới ghi có được các phiên bản cần thiết đọc đúng không? |
| **Schema** | Kiểu cột, độ dài, `NOT NULL`, `CHECK`, `UNIQUE` và index có hỗ trợ định dạng mới không? |
| **Truy vấn** | JPQL, native SQL, báo cáo và job có còn lọc/sắp xếp/nhóm dữ liệu đúng không? |
| **Triển khai đồng thời** | Khi bản cũ và bản mới cùng chạy, chúng có hiểu dữ liệu do nhau ghi không? |
| **Rollback** | Nếu cần quay về bản cũ, bản cũ còn đọc và ghi dữ liệu mới được không? |
| **Tích hợp** | CDC, ETL, event consumer, batch job hoặc hệ thống ngoài có đang dựa vào định dạng DB cũ không? |
| **Vận hành** | Backfill, cache, metric, backup và khả năng phát hiện dữ liệu không hợp lệ có sẵn không? |

Một thay đổi có thể **tương thích ở cấp Java nhưng không tương thích ở cấp dữ liệu**. Ví dụ, `AttributeConverter<OrderState, String>` vẫn giữ nguyên chữ ký sau khi đổi từ `"N"` sang `"NEW"`, nên dự án biên dịch bình thường; nhưng database vẫn chứa `"N"` và phần đọc mới chỉ hiểu `"NEW"`.

Ngược lại, có trường hợp cả phiên bản cũ và mới đều đọc được dữ liệu nhưng **không còn cùng hiểu ý nghĩa**. Đây là dạng nguy hiểm hơn lỗi parse vì có thể tạo kết quả nghiệp vụ sai mà không ném exception.

## 3. Dùng hai phép biến đổi để suy luận về khả năng tương thích

Có thể diễn đạt converter của phiên bản `v` thành hai hàm:

- `encode_v(x)`: chuyển giá trị miền nghiệp vụ `x` thành giá trị lưu trữ.
- `decode_v(y)`: chuyển dữ liệu lưu trữ `y` thành giá trị miền nghiệp vụ.

Ở phiên bản đầu:

```text
             encode_v1
OrderState.NEW ───────────> "N"
               <──────────
             decode_v1
```

Sau nâng cấp, nhóm phát triển muốn lưu tên đầy đủ:

```text
             encode_v2
OrderState.NEW ───────────> "NEW"
               <──────────
             decode_v2
```

Nếu converter mới **chỉ biết mã mới**, ta có:

```text
decode_v2("N") → lỗi
```

Vậy converter mới không tương thích với dữ liệu cũ.

### 3.1. Kiểm tra tương thích đọc dữ liệu cũ

Điều kiện mong muốn khi nâng cấp không làm mất dữ liệu là:

```text
decode_v2(encode_v1(x)) = x
```

cho **mọi giá trị `x` từng được lưu bằng phiên bản cũ**.

Đây là điều kiện về **bảo toàn ý nghĩa**, không chỉ là “converter không ném lỗi”. Một converter mới trả về `OrderState.NEW` cho mọi mã lạ có thể không lỗi nhưng vẫn diễn giải sai các trạng thái `SHIPPED` và `DELIVERED`.

### 3.2. Kiểm tra tương thích khi nhiều phiên bản cùng ghi

Nếu hai bản ứng dụng còn chạy đồng thời, phải xét chiều ngược:

```text
decode_v1(encode_v2(x)) = x
```

Nếu v2 bắt đầu ghi `"NEW"` nhưng v1 chỉ đọc `"N"`, điều kiện này không đúng. Điều đó có nghĩa bản v1 có thể gặp lỗi khi tải hàng do v2 vừa cập nhật.

Tương thích **đọc dữ liệu cũ** là cần cho nâng cấp; tương thích **đọc dữ liệu mới bởi bản cũ** là vấn đề riêng cho rolling deployment và rollback.

### 3.3. Kiểm tra round-trip

Bất kể phiên bản, một phép chuyển đổi không làm mất thông tin thường cần:

```text
decode_v(encode_v(x)) = x
```

cho tập giá trị nghiệp vụ được hỗ trợ.

Không phải mọi chuyển đổi đều đảo ngược được hoàn toàn. Ví dụ làm tròn số tiền, cắt chuỗi, bỏ timezone hoặc chuyển thời điểm chính xác tới giây sang chỉ còn ngày sẽ làm mất thông tin. Nếu thay đổi mới làm tròn nhiều hơn hoặc gộp các giá trị trước đây khác nhau, phải đánh giá xem việc mất thông tin có được nghiệp vụ chấp nhận không.

## 4. Ví dụ không tương thích: đổi mã trạng thái đã lưu

Ở phiên bản v1:

| Trạng thái | Mã v1 |
| --- | --- |
| `NEW` | `N` |
| `SHIPPED` | `S` |
| `DELIVERED` | `D` |

Phiên bản v2 quyết định dùng mã dài:

| Trạng thái | Mã v2 |
| --- | --- |
| `NEW` | `NEW` |
| `SHIPPED` | `SHIPPED` |
| `DELIVERED` | `DELIVERED` |

Nếu sửa converter một cách trực tiếp:

```java
@Override
public String convertToDatabaseColumn(OrderState state) {
    return state == null ? null : state.name();
}

@Override
public OrderState convertToEntityAttribute(String code) {
    return code == null ? null : OrderState.valueOf(code);
}
```

thì bản ghi đang có `state_code = 'S'` sẽ làm `OrderState.valueOf("S")` thất bại. Nếu cột trước đây là `VARCHAR(1)`, thao tác ghi `"SHIPPED"` còn có thể thất bại do vượt giới hạn độ dài.

Một thay đổi converter ngắn gọn có thể đồng thời gây:

1. **Lỗi đọc dữ liệu lịch sử**.
2. **Lỗi ghi do schema không phù hợp**.
3. **Lỗi trên bản ứng dụng cũ** nếu nó thấy mã mới.
4. **Lỗi truy vấn trực tiếp** nếu query vẫn so sánh `WHERE state_code = 'S'`.
5. **Lỗi trong các hệ thống ngoài** đang tiêu thụ cột `state_code` theo hợp đồng một ký tự.

Vì vậy, trước khi sửa converter cần xác định **định dạng đang được dùng ở đâu**, không chỉ xem class converter.

## 5. Phân loại thay đổi theo mức rủi ro

Không phải thay đổi nào cũng buộc migration. Có thể đánh giá theo các nhóm sau:

| Thay đổi | Ví dụ | Rủi ro chính |
| --- | --- | --- |
| Đổi code nội bộ, không đổi biểu diễn | Refactor converter nhưng `N/S/D` giữ nguyên | Lỗi regression, `null`, giá trị không hợp lệ |
| Mở rộng tập đọc, giữ nguyên tập ghi | Đọc cả `N` và `NEW`; vẫn ghi `N` | Thường phù hợp bước chuẩn bị chuyển đổi |
| Đổi biểu diễn khi ghi | `N` thành `NEW` | Bản cũ không đọc được; schema và truy vấn cần đổi |
| Thu hẹp tập giá trị đọc | Không còn hiểu `D` | Dữ liệu lịch sử có thể mất khả năng đọc |
| Đổi nghĩa một giá trị | `S` từ “shipped” thành “suspended” | Sai nghiệp vụ dù parse thành công |
| Gộp nhiều giá trị thành một | `PENDING` và `QUEUED` cùng thành `WAITING` | Mất khả năng phân biệt dữ liệu gốc |
| Thay đổi độ chính xác | `DECIMAL(19,4)` thành số nguyên xu | Làm tròn, tràn số, thay đổi so sánh |
| Đổi đơn vị | Millisecond thành second | Giá trị vẫn là số nhưng diễn giải sai theo hệ số 1000 |
| Đổi định dạng ngày giờ | Local time thành UTC | Sai thời điểm nếu không biết timezone cũ |
| Đổi serialization | JSON schema v1 thành v2 | Dữ liệu cũ và consumer ngoài không hiểu |
| Đổi khóa/thuật toán mã hóa | Ciphertext format v1 thành v2 | Không giải mã được lịch sử nếu mất metadata/key |
| Đổi mapping rộng bằng `autoApply` | Converter áp dụng tự động cho nhiều field | Ảnh hưởng cả thuộc tính không chủ đích |

Mức rủi ro cụ thể phụ thuộc dữ liệu hiện hữu và kiến trúc triển khai. Không nên kết luận “thay đổi nhỏ” chỉ dựa trên số dòng Java bị sửa.

## 6. Đọc được chưa chắc đã tương thích về mặt nghiệp vụ

Hãy tưởng tượng một converter số tiền đang lưu `BigDecimal` với đơn vị **đồng**:

```text
Database amount = 150000
Domain Money = 150000 VND
```

Phiên bản mới quyết định coi giá trị lưu trữ là **nghìn đồng** để giảm kích thước:

```text
Database amount = 150000
Domain Money = 150000000 VND  ← sai nếu không migration
```

Kiểu cột vẫn là số, chuyển đổi Java có thể chạy không lỗi. Nhưng ý nghĩa thay đổi theo hệ số 1000.

Một ví dụ khác là chuẩn hóa mã khách hàng:

```text
v1: "ab01" và "AB01" được giữ như hai giá trị phân biệt
v2: normalize(value) = uppercase(value)
```

Nếu sau thay đổi cả hai đều thành `"AB01"`, converter mới đã **gộp hai giá trị khác nhau**. Điều này có thể phá vỡ `UNIQUE`, khóa tìm kiếm, liên kết dữ liệu và các quy tắc nghiệp vụ.

Do đó, đánh giá tương thích cần xem xét:

- Dữ liệu có giữ nguyên **đơn vị** không?
- Độ chính xác hoặc phần thông tin nào bị mất?
- Hai giá trị trước đây khác nhau có bị gộp thành một không?
- Giá trị khác nhau có bị hiểu như cùng một trạng thái không?
- Có quy ước về chữ hoa/chữ thường, khoảng trắng, dấu, collation, locale hay timezone không?
- `null`, chuỗi rỗng và “giá trị chưa biết” được phân biệt thế nào?

**Đọc thành công** chỉ là điều kiện kỹ thuật. **Đúng ý nghĩa** mới là mục tiêu của persistence.

## 7. Đánh giá tập dữ liệu đã tồn tại trước khi đổi quy tắc

Trước migration, cần biết dữ liệu đang chứa những biểu diễn nào, có bao nhiêu bản ghi và các trường hợp bất thường là gì.

Với cột `state_code`:

```sql
SELECT state_code, COUNT(*) AS total
FROM orders
GROUP BY state_code
ORDER BY state_code;
```

Kết quả giả định:

| `state_code` | `total` |
| --- | ---: |
| `N` | 12540 |
| `S` | 4860 |
| `D` | 7620 |
| `NULL` | 3 |
| `X` | 12 |

Khi đó, không thể chỉ lập mapping cho `N/S/D` rồi tuyên bố toàn bộ dữ liệu tương thích. Còn ba hàng `NULL` và mười hai hàng `X` cần tìm nguồn gốc. Chúng có thể là dữ liệu lỗi, giá trị từ phiên bản rất cũ, thao tác SQL trực tiếp hoặc một extension không còn được tài liệu hóa.

Truy vấn các mã ngoài tập dự kiến:

```sql
SELECT id, state_code
FROM orders
WHERE state_code IS NULL
   OR state_code NOT IN ('N', 'S', 'D');
```

Nếu cần so khớp theo giá trị gốc, cũng cần chú ý hệ quản trị có thể áp dụng collation hoặc xử lý trailing spaces khác nhau. Ví dụ chuỗi `"s"` và `"S"` có thể được so sánh giống hoặc khác tùy cột/query.

Đối với thay đổi giá trị tiền, ngày giờ hoặc định dạng phức tạp, khảo sát tương ứng có thể gồm:

- `MIN`, `MAX`, giá trị âm, bằng 0, rất lớn, số chữ số sau dấu thập phân.
- Phân bố dữ liệu theo thời gian, thời kỳ sử dụng từng phiên bản ứng dụng.
- Số bản ghi không parse được hoặc không có timezone.
- Các giá trị bị trùng sau chuẩn hóa.
- Dữ liệu đã lưu với nhiều định dạng khác nhau trong cùng một cột.

Việc khảo sát phải thực hiện trên dữ liệu có quyền truy cập phù hợp và bảo vệ thông tin nhạy cảm. Các ví dụ trong bài sử dụng giá trị giả lập để tập trung vào quy tắc chuyển đổi.

## 8. Đánh giá tương thích với schema và ràng buộc

Converter hoạt động trong code Java, còn database kiểm soát **kiểu cột, độ dài, khóa, ràng buộc và index**.

### 8.1. Độ dài và kiểu cột

Trước khi đổi `"S"` thành `"SHIPPED"`, schema có thể là:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    state_code VARCHAR(1) NOT NULL
);
```

Phải mở rộng độ dài cột **trước khi** có instance ghi mã dài. Ví dụ ở PostgreSQL:

```sql
ALTER TABLE orders
ALTER COLUMN state_code TYPE VARCHAR(16);
```

Cú pháp DDL này phụ thuộc PostgreSQL; với MySQL, Oracle hoặc SQL Server cần cách thực hiện tương ứng. Ngoài độ dài, phải kiểm tra constraint có đang giới hạn mã một ký tự không.

### 8.2. `CHECK` và khóa ngoại

Nếu schema có:

```sql
CHECK (state_code IN ('N', 'S', 'D'))
```

thì mọi thao tác ghi `"SHIPPED"` sẽ thất bại cho tới khi constraint được mở rộng hoặc thay đổi. Không nên tự động bỏ hết ràng buộc để “cho ứng dụng chạy được”. Thay vào đó, hãy lên kế hoạch cho giai đoạn chấp nhận cả **mã cũ** và **mã mới**, rồi thu hẹp khi dữ liệu đã chuyển hoàn toàn.

Nếu giá trị được ánh xạ sang một **mã trong bảng tham chiếu**, phải cập nhật các hàng tham chiếu và foreign key theo trình tự thích hợp. Trong một số trường hợp, thiết kế bảng mã ổn định giúp tránh phải đổi converter thường xuyên.

### 8.3. `UNIQUE` và index

Thay đổi kiểu chữ hoặc chuẩn hóa giá trị có thể tạo xung đột:

```text
DB cũ: "ab01", "AB01" (hai chuỗi khác nhau theo quy tắc cũ)
Sau chuẩn hóa: "AB01", "AB01" (trùng)
```

Một index unique được tạo trên biểu diễn mới có thể thất bại; hoặc code mới có thể gộp hai tài khoản mà hệ thống cũ coi là khác biệt. Cần kiểm tra collisions **trước** khi đổi quy tắc đọc/ghi.

Index phục vụ `WHERE` hoặc `ORDER BY` cũng cần đánh giá lại khi đổi kiểu `VARCHAR` sang `INTEGER`, khi thêm phép chuyển đổi tại thời điểm truy vấn hoặc khi thay đổi collation. Một converter “đúng” nhưng làm query không còn dùng index phù hợp vẫn gây rủi ro vận hành.

## 9. Dùng converter chuyển tiếp để đọc cả định dạng cũ và mới

Để chuyển `N/S/D` sang tên đầy đủ mà không làm code mới mất khả năng đọc bản ghi cũ, trước hết có thể mở rộng **phía đọc**.

Ví dụ:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class CompatibleOrderStateConverter
        implements AttributeConverter<OrderState, String> {

    @Override
    public String convertToDatabaseColumn(OrderState state) {
        if (state == null) return null;

        // Giai đoạn đầu vẫn ghi định dạng cũ.
        return switch (state) {
            case NEW       -> "N";
            case SHIPPED   -> "S";
            case DELIVERED -> "D";
        };
    }

    @Override
    public OrderState convertToEntityAttribute(String code) {
        if (code == null) return null;

        return switch (code) {
            case "N", "NEW"             -> OrderState.NEW;
            case "S", "SHIPPED"         -> OrderState.SHIPPED;
            case "D", "DELIVERED"       -> OrderState.DELIVERED;
            default -> throw new IllegalArgumentException(
                "Unknown order state code: " + code
            );
        };
    }
}
```

Converter này có hai đặc điểm:

1. **Đọc được cả hai định dạng**: `"N"` và `"NEW"` đều trở thành `OrderState.NEW`.
2. **Vẫn ghi mã cũ**: `OrderState.NEW` được lưu thành `"N"`.

Điều này giúp triển khai thay đổi khả năng đọc trước. Tuy vậy, converter hai chiều có thể đồng thời xuất hiện dưới nhiều phiên bản trong hệ thống; cần xác định khi nào được phép đổi phía ghi.

### Vì sao không đổi phía ghi ngay trong lần deploy đầu tiên?

Giả sử có hai instance:

```text
Instance A: v1 — chỉ đọc "N", "S", "D"
Instance B: v2 — đọc "N"/"NEW", nhưng đã ghi "NEW"
```

Nếu B cập nhật bản ghi thành `"NEW"`, A có thể không đọc được. Trong rolling deployment, **bản v2 nên đọc rộng hơn trước, nhưng tiếp tục ghi định dạng mà bản v1 đọc được** cho tới khi không còn instance v1 hoặc consumer bắt buộc dùng mã cũ.

Điều kiện này cũng áp dụng cho batch job, consumer nền và dịch vụ khác có thể không được nâng cấp cùng lúc với web application.

## 10. Chiến lược triển khai theo giai đoạn: mở rộng → chuyển đổi → thu hẹp

Với hệ thống cần duy trì khả năng hoạt động trong quá trình nâng cấp, một hướng thông dụng là **expand–migrate–contract**.

```text
Trạng thái ban đầu
    Dữ liệu: N/S/D
    Ứng dụng: chỉ đọc/ghi N/S/D
                 │
                 ▼
Bước 1 — Expand schema
    Cột/constraint chấp nhận N/S/D và NEW/SHIPPED/DELIVERED
                 │
                 ▼
Bước 2 — Expand reader
    Tất cả ứng dụng đọc được cả hai
    Vẫn ghi N/S/D
                 │
                 ▼
Bước 3 — Switch writer
    Chỉ khi không còn reader cũ:
    bắt đầu ghi NEW/SHIPPED/DELIVERED
                 │
                 ▼
Bước 4 — Migrate history
    Backfill dữ liệu N/S/D thành mã mới
    Theo dõi writer cũ và dữ liệu phát sinh
                 │
                 ▼
Bước 5 — Contract
    Chỉ còn dữ liệu mới và tất cả consumer đã nâng cấp
    Thu hẹp converter/constraint, loại bỏ mã cũ
```

### Bước 1: chuẩn bị schema

Mở rộng cột `VARCHAR(1)` thành chiều dài đủ cho `DELIVERED`; thay đổi constraint để trong giai đoạn chuyển tiếp cho phép cả:

```text
N, S, D, NEW, SHIPPED, DELIVERED
```

Thao tác DDL phải được chuẩn bị cho database đang dùng, có phương án triển khai và rollback thích hợp. Không thực hiện đổi kiểu cột trên bảng lớn trong giờ cao điểm khi chưa ước lượng lock và thời gian migration.

### Bước 2: triển khai reader tương thích

Deploy converter có thể đọc cả mã cũ và mã mới nhưng vẫn ghi mã cũ. Khi còn instance v1 chỉ hiểu mã cũ, chưa chuyển writer.

Bước này cũng phải cập nhật **các reader khác** như service, job, báo cáo, data pipeline. Chỉ kiểm tra hết instance HTTP chưa đủ nếu một nightly job vẫn xử lý định dạng cũ.

### Bước 3: đổi phía ghi sang mã mới

Sau khi xác nhận tất cả reader cần thiết đã hiểu định dạng mới, cập nhật:

```java
@Override
public String convertToDatabaseColumn(OrderState state) {
    return state == null ? null : state.name();
}
```

và giữ bộ giải mã đọc cả mã cũ lẫn mã mới. Lúc này database có thể đồng thời chứa hai dạng vì dữ liệu lịch sử vẫn là mã cũ.

Tùy kiến trúc, việc bật writer mới có thể thực hiện bằng một phiên bản ứng dụng kế tiếp hoặc feature flag được quản lý chặt chẽ. Nếu dùng feature flag, phải bảo đảm toàn bộ node/worker không bắt đầu ghi mã mới khi còn consumer không hiểu.

### Bước 4: backfill dữ liệu cũ

Ví dụ SQL minh họa:

```sql
UPDATE orders
SET state_code = CASE state_code
    WHEN 'N' THEN 'NEW'
    WHEN 'S' THEN 'SHIPPED'
    WHEN 'D' THEN 'DELIVERED'
    ELSE state_code
END
WHERE state_code IN ('N', 'S', 'D');
```

Trên bảng lớn, cần backfill có kiểm soát theo lô để tránh transaction quá lớn, lock kéo dài và áp lực replication. Nếu có ứng dụng cũ ghi đồng thời, backfill có thể bị “đảo ngược” bởi các bản ghi mới tiếp tục dùng mã cũ. Đó là lý do xác định thời điểm chuyển writer và theo dõi nguồn ghi quan trọng.

### Bước 5: thu hẹp hỗ trợ

Khi dữ liệu cũ đã hết, mọi writer đều ghi mã mới và không còn nhu cầu rollback sang bản không hiểu mã mới, có thể:

- Loại bỏ nhánh đọc mã `N/S/D` nếu hợp đồng mới cho phép.
- Thu hẹp `CHECK` để chỉ chấp nhận mã mới.
- Xóa code chuyển tiếp hoặc feature flag đã hết vai trò.
- Cập nhật tài liệu schema và hợp đồng tích hợp.

**Không thu hẹp quá sớm.** Giữ khả năng đọc dữ liệu cũ thêm một thời gian có thể là quyết định hợp lý nếu còn backup, job khôi phục hoặc sự kiện cũ được replay.

## 11. Đánh giá rollback trước khi chuyển writer

Rollback application thường được xem là “triển khai lại bản trước”. Với converter, điều đó chỉ an toàn nếu bản trước còn hiểu định dạng đã được ghi trong thời gian chạy bản mới.

Ví dụ:

```text
10:00  Deploy v2, bắt đầu ghi "SHIPPED"
10:10  Một số bản ghi đã chứa "SHIPPED"
10:15  Phát hiện lỗi, rollback về v1 chỉ hiểu "S"
10:16  v1 đọc các bản ghi mới → lỗi
```

Một bản rollback code thành công về mặt triển khai **chưa phải rollback dữ liệu**.

Có một số chiến lược khả thi tùy yêu cầu:

1. **Trì hoãn writer mới** đến khi giai đoạn rollback về bản cũ không còn cần thiết.
2. **Có một bản cầu nối** hiểu cả cũ và mới để làm mục tiêu rollback an toàn.
3. **Chuẩn bị rollback dữ liệu** nếu có thể chuyển ngược không mất thông tin và hệ thống có thể kiểm soát ghi.
4. **Tách biểu diễn mới sang cột mới** nếu việc đổi tại chỗ không thể hỗ trợ hai bản ứng dụng cùng lúc.
5. **Chấp nhận hướng triển khai chỉ tiến** sau khi vượt điểm không thể rollback, kèm kế hoạch sửa lỗi tiếp theo thay vì quay về mã không đọc được dữ liệu.

Trước khi quyết định, hỏi rõ: **“Khi chúng ta nhấn rollback, dữ liệu đã ghi bởi phiên bản mới sẽ được ai giải mã?”**

## 12. Khi nào cần thêm cột mới thay vì đổi dữ liệu tại chỗ?

Đổi tại chỗ một cột dễ triển khai khi:

- Định dạng mới có thể cùng tồn tại với định dạng cũ trong một cột.
- Có ánh xạ một-một chính xác giữa hai định dạng.
- Có thể nâng cấp reader và writer có kiểm soát.
- Migration không gây lock, xung đột và tác động vận hành vượt mức chấp nhận.

Ngược lại, nên cân nhắc **thêm cột mới** khi đổi kiểu biểu diễn đáng kể:

```text
amount_text      -> amount_minor_units
local_time_text  -> occurred_at_utc
payload_v1       -> payload_v2
encrypted_v1     -> encrypted_v2
```

Ví dụ chuyển giá trị tiền sang đơn vị nhỏ nhất:

```sql
ALTER TABLE invoices
ADD COLUMN amount_minor_units BIGINT;
```

Sau đó cần định nghĩa phép chuyển giá trị cũ sang cột mới, backfill, duy trì ghi đồng thời nếu cần, chuyển reader, xác nhận độ chính xác rồi mới bỏ cột cũ.

Với tiền tệ, **không phải mọi đồng tiền đều có cùng số chữ số phần lẻ**. Nếu dùng đơn vị nhỏ nhất, cần một quy tắc rõ ràng cho từng loại tiền, precision, scale và rounding. Không nên mặc định nhân mọi giá trị `BigDecimal` với `100`.

Thêm cột giúp kiểm tra hai biểu diễn song song và có đường rollback rõ hơn, nhưng tăng chi phí vận hành, đồng bộ và thời gian chuyển tiếp. Đây là lựa chọn thiết kế chứ không phải quy tắc luôn đúng.

## 13. Thay đổi converter giá trị tiền: đánh giá độ chính xác

Xét một value object:

```java
public record Money(java.math.BigDecimal amount) {
    public Money {
        if (amount == null) {
            throw new IllegalArgumentException("amount");
        }
    }
}
```

Giả sử phiên bản cũ lưu số thập phân chính xác:

```text
Domain:  12.3456
DB:      DECIMAL(19, 4) = 12.3456
```

Phiên bản mới muốn lưu đơn vị nhỏ nhất dạng số nguyên với hai chữ số phần lẻ:

```text
Domain:  12.3456
DB mới:  1235 (nếu làm tròn HALF_UP)
Load:    12.35
```

Phép chuyển mới không giữ nguyên giá trị `12.3456`. Nếu hệ thống đang dùng bốn chữ số phần lẻ cho tỷ giá hoặc thuế, phép đổi này có thể làm sai tính toán.

Đánh giá cần phân biệt:

- **Độ chính xác lưu trữ:** scale và precision của `DECIMAL` cũ và số nguyên mới.
- **Chính sách làm tròn:** `HALF_UP`, `HALF_EVEN` hoặc quy tắc nghiệp vụ khác.
- **Giá trị lớn:** có thể vượt giới hạn `long` sau khi nhân hệ số.
- **Giá trị âm:** có được chấp nhận không; cách làm tròn số âm thế nào?
- **Tiền tệ:** có cần lưu mã `currency` để hiểu số lượng đơn vị nhỏ nhất?
- **Query:** `SUM`, `AVG`, `ORDER BY` và báo cáo sẽ thay đổi cách tính hay không?
- **Dữ liệu lịch sử:** có thể chuyển chính xác hay phải xác nhận mức sai lệch được phép?

Nếu một chuyển đổi làm mất thông tin, phải ghi nhận rằng **không thể rollback hoàn hảo chỉ bằng converter nghịch đảo**. Việc không thể khôi phục dữ liệu gốc là một quyết định nghiệp vụ và lưu trữ, không phải lỗi cú pháp JPA.

## 14. Thay đổi thời gian và timezone: dữ liệu có thể vẫn là timestamp nhưng khác nghĩa

Một hệ thống cũ lưu thời gian theo giờ địa phương:

```text
DB: 2026-11-15 09:00:00
Ý nghĩa cũ: 09:00 tại Asia/Ho_Chi_Minh
```

Phiên bản mới muốn mọi thời điểm được hiểu là UTC:

```text
DB: 2026-11-15 09:00:00
Ý nghĩa mới: 09:00 UTC
```

Chuỗi và kiểu SQL có thể giống hệt nhau, nhưng hai thời điểm cách nhau bảy giờ. Nếu chỉ đổi converter hoặc cấu hình JDBC timezone mà không chuyển dữ liệu, lịch hẹn, thứ tự sự kiện và SLA có thể sai.

Khi đánh giá phải biết:

1. Dữ liệu cũ biểu diễn **instant** hay **local date-time**?
2. Timezone gốc có được lưu kèm không hay chỉ được suy từ cấu hình server?
3. Dữ liệu trải qua những thời kỳ đổi múi giờ hoặc daylight-saving time không?
4. Giá trị ambiguous/nonexistent tại các vùng có DST được xử lý ra sao?
5. Kết quả tương thích với `Instant`, `OffsetDateTime`, `LocalDateTime` và loại cột đang sử dụng không?
6. Có app hoặc hệ thống khác đang tự suy timezone từ cột này không?

Không nên “sửa” dữ liệu bằng cách cộng/trừ một số giờ cố định cho mọi khu vực, mọi năm, nếu dữ liệu phụ thuộc timezone có quy tắc lịch sử khác nhau.

## 15. Đổi định dạng JSON hoặc chuỗi tuần tự hóa

Một value object có thể được chuyển thành JSON rồi lưu vào cột chuỗi hoặc JSON native:

```json
{
  "street": "12 Main St",
  "city": "Hanoi"
}
```

Sau đó schema v2 đổi tên trường:

```json
{
  "line1": "12 Main St",
  "city": "Hanoi",
  "countryCode": "VN"
}
```

Vấn đề không còn chỉ là đổi mapper Java. Cần xác định:

- Parser v2 có đọc `street` cũ không?
- Nếu `countryCode` chưa từng được lưu, giá trị mặc định nào đúng theo dữ liệu gốc?
- Parser v1 có xử lý field `line1` và `countryCode` mới không?
- Các hệ thống ETL hoặc dashboard có truy xuất JSON path `$.street` không?
- Có cần đặt `formatVersion` trong payload để phân biệt nhiều định dạng lâu dài không?

Ví dụ chiến lược có phiên bản:

```json
{
  "formatVersion": 2,
  "line1": "12 Main St",
  "city": "Hanoi",
  "countryCode": "VN"
}
```

Nếu dữ liệu cũ không có `formatVersion`, converter phải có quy tắc nhận diện rõ ràng, chẳng hạn coi vắng mặt version là cấu trúc v1 **chỉ khi giả định đó thực sự đúng với dữ liệu lịch sử**.

Một thông lệ hữu ích là **đọc nhiều phiên bản, ghi một định dạng chuẩn** sau khi đã làm rõ khả năng tương thích với consumer cũ. Tuy vậy, đọc nhiều phiên bản mãi mãi có chi phí; cần chính sách duy trì và loại bỏ định dạng cũ.

## 16. Mã hóa, masking và nén là các chuyển đổi nhạy cảm với metadata

Một converter có thể biến plaintext thành ciphertext hoặc nén dữ liệu để lưu trữ. Khi thay thuật toán hoặc key, đừng giả định một ciphertext cũ sẽ được giải mã tự động bởi converter mới.

Ví dụ về dạng metadata khái niệm:

```text
v1:<key-id>:<ciphertext>
v2:<key-id>:<nonce>:<ciphertext-and-auth-tag>
```

Điều cần đánh giá là khả năng nhận diện **version, key-id, metadata giải mã** và đường đi khôi phục dữ liệu cũ. Việc thay format nên giữ khả năng đọc những bản ghi được tạo trước ngày chuyển đổi trong thời gian cần thiết.

Các lưu ý kiến trúc:

- Không dùng cùng một giá trị mặc định cho dữ liệu giải mã thất bại và dữ liệu thật sự rỗng.
- Không ghi plaintext nhạy cảm ra log chỉ để debug converter.
- Giữ quản lý khóa và vòng đời khóa tách khỏi logic nghiệp vụ.
- Có tiêu chí xử lý bản ghi không chuyển đổi được trước khi hủy key cũ.
- Đảm bảo hệ thống backup/restore có thể dùng metadata và khóa phù hợp với dữ liệu tại thời điểm backup.

Với dữ liệu quan trọng, thất bại trong tương thích converter có thể làm **không thể đọc lại dữ liệu đã lưu**, chứ không chỉ làm chậm truy vấn.

## 17. Tác động đến JPQL, Criteria API, native SQL và báo cáo

Một `AttributeConverter` thường được provider áp dụng cho giá trị thuộc tính được ánh xạ khi đọc, ghi và xử lý tham số truy vấn theo ngữ nghĩa chuẩn. Vì vậy, truy vấn JPQL theo kiểu miền nghiệp vụ thường dễ duy trì hơn việc hard-code mã DB.

Ví dụ:

```java
List<PurchaseOrder> shipped = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.state = :state",
    PurchaseOrder.class
).setParameter("state", OrderState.SHIPPED)
 .getResultList();
```

Tham số có kiểu `OrderState`, còn provider có thể chuyển sang mã lưu trữ theo converter.

Nhưng có một vấn đề chuyển tiếp: **nếu cùng một trạng thái được lưu bằng cả `"S"` và `"SHIPPED"`**, converter phía ghi chỉ phát ra một biểu diễn, chẳng hạn `"SHIPPED"`. Khi đó điều kiện SQL tương ứng có thể là:

```sql
WHERE state_code = 'SHIPPED'
```

Truy vấn này **không tự tìm được các hàng cũ chứa `"S"`** chỉ vì phía đọc converter hiểu cả hai dạng.

Đây là điểm dễ bỏ sót:

> **Khả năng decode nhiều định dạng không đồng nghĩa với khả năng tìm kiếm tất cả các định dạng ấy bằng một phép so sánh trên cột.**

Trong giai đoạn mixed-format, cần thiết kế cách giải quyết rõ ràng:

- Giữ chỉ một định dạng ghi và chưa trộn dữ liệu cho tới khi có kế hoạch truy vấn.
- Backfill dữ liệu có kiểm soát trước khi bật các query phụ thuộc mã mới.
- Dùng truy vấn tạm thời nhận cả mã cũ và mới nếu phù hợp, và loại bỏ khi migration xong.
- Dùng cột canonical/normalized bổ sung trong những kiến trúc có yêu cầu tra cứu cao.

Đặc biệt phải rà soát:

| Nơi sử dụng | Ảnh hưởng có thể xảy ra |
| --- | --- |
| JPQL `WHERE property = :value` | Tham số có thể encode thành một định dạng, bỏ sót hàng lưu dạng khác |
| JPQL/Criteria `ORDER BY` | Thứ tự chuỗi/số của biểu diễn mới có thể khác |
| Native SQL | Giá trị mã DB thường được hard-code trong query |
| SQL view và materialized view | Cần đổi điều kiện, phép nhóm hoặc logic refresh |
| Báo cáo và BI | Dashboard có thể nhóm `"S"` và `"SHIPPED"` thành hai trạng thái |
| Batch update SQL trực tiếp | Bỏ qua converter JPA, có thể tiếp tục ghi mã cũ |
| Index và constraint | Có thể cần thay đổi theo kiểu/format mới |
| Cache và search index | Có thể giữ giá trị cũ hoặc không đồng bộ cùng transaction |

Một số provider có cách mở rộng query chuyên biệt; khi dùng cần ghi nhận phụ thuộc phiên bản thay vì giả định JPA chuẩn sẽ tự tái viết mọi phép lọc theo cả hai kiểu dữ liệu.

## 18. Tương thích cache và persistence context

Persistence context giữ những entity được quản lý trong phạm vi hoạt động của `EntityManager`. Cache cấp hai, nếu bật, còn có thể giữ trạng thái entity giữa các context và transaction theo cơ chế provider.

Khi converter thay đổi, cần xem:

- Cache chứa **giá trị Java đã convert** hay biểu diễn nội bộ khác?
- Cache entry được tạo bởi phiên bản cũ có còn hợp lệ với code mới không?
- Có nhiều node dùng chung cache nhưng chạy hai phiên bản converter khác nhau không?
- Khi backfill trực tiếp bằng SQL, cache có bị stale không?
- Có cần evict cache hoặc đổi namespace/cache region để tránh dùng lại dữ liệu không tương thích?

Không nên mặc định `UPDATE` từ migration SQL làm mọi cached entity tự cập nhật. Cache ngoài database và persistence context có vòng đời riêng.

Ở mức API chuẩn, `EntityManagerFactory.getCache()` cho phép thao tác evict trong những môi trường hỗ trợ shared cache. Nhưng cơ chế invalidation, cache region và bảo đảm đồng bộ cần được kiểm tra theo provider/cache implementation thực tế.

## 19. Thay đổi `autoApply` và phạm vi converter

Converter JPA có thể được khai báo:

```java
@Converter(autoApply = true)
public class SomeValueConverter
        implements AttributeConverter<SomeValue, String> {
    // ...
}
```

`autoApply = true` khiến provider tự áp dụng converter cho các thuộc tính tương thích về kiểu theo quy tắc của JPA, trong phạm vi áp dụng được hỗ trợ. Điều đó tiện lợi nhưng cũng có thể khiến **một thay đổi converter ảnh hưởng nhiều entity cùng lúc**.

Ví dụ, `CurrencyCode` được dùng ở:

```text
Invoice.currency
Payment.currency
Refund.currency
ReportSnapshot.baseCurrency
```

Nếu cùng một converter áp dụng rộng và đổi biểu diễn từ `"VND"` thành `"704"`, tất cả bảng/cột liên quan có thể bị ảnh hưởng. Không nên chỉ sửa converter rồi kiểm tra mỗi `Invoice`.

Với converter áp dụng tường minh:

```java
@Convert(converter = CurrencyCodeConverter.class)
private CurrencyCode currency;
```

phạm vi thường dễ quan sát hơn, nhưng vẫn phải kiểm tra các nơi cùng tham chiếu converter. Cần đặc biệt thận trọng khi thuộc tính dùng `@Enumerated`, vì mapping enum và `AttributeConverter` là hai cơ chế khác nhau; không nên đặt cả hai lên cùng một thuộc tính với kỳ vọng chúng tự phối hợp.

Phạm vi ảnh hưởng là một đầu vào quan trọng cho đánh giá tương thích: **một class converter có thể định nghĩa hợp đồng lưu trữ của rất nhiều cột**.

## 20. Chiến lược xử lý dữ liệu lạ khi chuyển đổi

Trong quá trình migration, converter có thể gặp mã chưa được nhận diện:

```java
@Override
public OrderState convertToEntityAttribute(String code) {
    if (code == null) return null;

    return switch (code) {
        case "N", "NEW" -> OrderState.NEW;
        case "S", "SHIPPED" -> OrderState.SHIPPED;
        case "D", "DELIVERED" -> OrderState.DELIVERED;
        default -> throw new IllegalArgumentException(
            "Unsupported state code: " + code
        );
    };
}
```

Quyết định ném exception ở đây làm dữ liệu bất thường lộ rõ, tránh đọc nhầm sang một trạng thái hợp lệ. Nhưng chính sách xử lý phải phù hợp với use case:

- **Dữ liệu giao dịch cốt lõi:** thường cần phát hiện sớm, chặn việc diễn giải sai.
- **Import từ bên ngoài:** có thể cần cách ly bản ghi lỗi để xử lý tiếp.
- **Giá trị tùy chọn trên màn hình:** có thể chấp nhận hiển thị “chưa xác định” nếu nghiệp vụ cho phép.
- **Mô hình có trạng thái `UNKNOWN` thực sự:** chỉ được dùng nếu ý nghĩa đã được định nghĩa rõ, không để che giấu lỗi chuyển đổi tùy tiện.

Cần phân biệt `null` là “không có giá trị” theo domain hay là vi phạm dữ liệu. Việc converter trả về `null` cho mọi mã lạ có thể làm mất thông tin và gây lỗi ở nơi khác, khiến nguồn gốc khó truy vết.

Nếu thiết kế bắt buộc hỗ trợ giá trị chưa biết mà vẫn muốn round-trip, có thể cân nhắc **value type chứa raw code** thay vì enum cố định. Khi đó ứng dụng giữ mã gốc để không mất thông tin, nhưng đổi lại mô hình domain và quy tắc sử dụng cũng phải được điều chỉnh.

## 21. Tính xác định, tính ổn định và tác dụng phụ của converter

Một converter được dùng trong persistence nên có hành vi càng **xác định** càng tốt: cùng một giá trị đầu vào và cùng phiên bản cấu hình thì cho cùng một biểu diễn lưu trữ.

Ví dụ nguy hiểm:

```java
@Override
public String convertToDatabaseColumn(Code code) {
    return java.time.Instant.now() + ":" + code.value();
}
```

Mỗi lần ghi cùng một `Code` có thể tạo giá trị khác nhau. Việc so sánh, index, unique và query equality có thể không còn hành vi mong muốn.

Cần thận trọng nếu converter:

- Phụ thuộc timezone mặc định của server.
- Phụ thuộc locale hoặc charset mặc định.
- Đọc cấu hình thay đổi theo node mà không có version rõ ràng.
- Có side effect như gọi API, phát event hoặc ghi audit log.
- Dùng tính ngẫu nhiên khi biểu diễn dữ liệu cần so sánh theo giá trị.
- Tự thay đổi giá trị domain trong quá trình encode/decode.

Với một số bài toán như mã hóa xác thực có nonce ngẫu nhiên, **tính không xác định là chủ đích bảo mật**. Khi đó phải thiết kế lại cách query/search và hợp đồng dữ liệu phù hợp; không nên dùng phép so sánh trực tiếp ciphertext để giả định tìm được các giá trị plaintext bằng nhau.

Nếu converter tạo ra sự khác biệt theo môi trường, rolling deployment càng khó đánh giá tương thích vì hai node chạy cùng code có thể ghi các biểu diễn khác nhau.

## 22. Kiểm thử nào cần có trước khi thay đổi quy tắc?

Trong giai đoạn xây dựng tính năng, bài toán quan trọng là xác nhận **tương thích lịch sử** bằng dữ liệu mang định dạng thật của các phiên bản trước. Chỉ kiểm thử giá trị vừa ghi rồi vừa đọc bằng converter mới là chưa đủ.

### 22.1. Ma trận đọc/ghi theo phiên bản

Giả sử có ba phiên bản:

- **v1:** đọc/ghi mã cũ `N/S/D`.
- **v2:** đọc cả cũ và mới, vẫn ghi mã cũ.
- **v3:** đọc cả cũ và mới, bắt đầu ghi mã mới.

Ma trận khái niệm:

| Reader | Dữ liệu do v1 ghi | Dữ liệu do v2 ghi | Dữ liệu do v3 ghi |
| --- | --- | --- | --- |
| v1 | Đọc được | Đọc được | **Không bảo đảm** |
| v2 | Đọc được | Đọc được | Đọc được |
| v3 | Đọc được | Đọc được | Đọc được |

Vì v2 vẫn ghi mã cũ nên v1 đọc được dữ liệu do v2 ghi. Nhưng khi v3 bắt đầu ghi mã mới, v1 chưa chắc đọc được. Do đó, v3 chỉ nên phát huy khả năng ghi mới sau khi hệ thống không còn reader v1 cần truy cập dữ liệu ấy.

### 22.2. Tập trường hợp cần được biểu diễn

| Trường hợp | Kỳ vọng |
| --- | --- |
| Bản ghi cũ có mã hợp lệ | Converter mới khôi phục đúng domain value |
| Bản ghi mới có mã mới hợp lệ | Converter mới khôi phục đúng domain value |
| `null` và chuỗi rỗng | Hành vi đúng hợp đồng, không tự đánh đồng tùy tiện |
| Mã không nhận diện | Lỗi hoặc xử lý theo chính sách có chủ đích |
| Giá trị sát giới hạn | Không tràn số, mất precision hoặc vượt độ dài cột |
| Dữ liệu khác chữ hoa/thường | Theo đúng quy tắc case-sensitive/collation |
| Hai bản ứng dụng cùng chạy | Không ghi mã khiến reader cần thiết bị lỗi |
| Query lọc theo thuộc tính | Tìm đúng cả dữ liệu cũ/mới hoặc có bước migration bảo đảm |
| Native SQL, báo cáo, batch job | Không giữ điều kiện mã cũ đã lỗi thời |
| Backfill chạy lại | Không làm biến dạng dữ liệu đã chuyển |
| Rollback theo kế hoạch | Bản rollback đọc được dữ liệu đã phát sinh |
| Cache có dữ liệu trước migration | Không trả về state sai hoặc stale |

### 22.3. Đọc fixture của dữ liệu cũ

Một bài kiểm tra có giá trị là tạo dữ liệu trực tiếp theo format v1, sau đó dùng bản ứng dụng v2/v3 để đọc:

```sql
INSERT INTO orders(id, state_code)
VALUES (101, 'N'), (102, 'S'), (103, 'D');
```

Trong một integration test được cấu hình với schema phù hợp:

```java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, 102L);

assertEquals(OrderState.SHIPPED, order.getState());
```

Đây là minh họa kiểm thử lịch sử; entity cần có getter `getState()` và mapping tương ứng. Bài thử mang ý nghĩa khác với round-trip test chỉ gọi `convertToDatabaseColumn` rồi `convertToEntityAttribute` cùng một converter.

### 22.4. Kiểm thử query trong giai đoạn mixed-format

Khi database có cả `"S"` và `"SHIPPED"`, cần xác nhận query phục vụ nghiệp vụ tìm được **tất cả** bản ghi phù hợp. Nếu query chỉ encode `OrderState.SHIPPED` thành `"SHIPPED"`, nó có thể bỏ qua `"S"`. Kiểm thử này giúp phát hiện lỗi mà một converter unit test thuần túy không nhận ra.

### 22.5. Kiểm thử migration

Các bài kiểm tra migration nên bao gồm:

- Chạy trên snapshot/schema có dạng dữ liệu cũ.
- Kiểm tra số bản ghi trước và sau, trạng thái null/invalid.
- Đối chiếu ý nghĩa trước và sau cho các mẫu đại diện.
- Kiểm tra constraint/index sau khi chuyển đổi.
- Chạy lại nếu migration thiết kế idempotent.
- Thử rollback hoặc kế hoạch phục hồi phù hợp.
- Với bảng lớn, đánh giá lock, transaction log, replication lag và thời lượng theo lô.

Các phép thử này thuộc quy trình đánh giá thay đổi ứng dụng, tách biệt với việc một file bài học Markdown được tạo thành công.

## 23. Dùng bảng quyết định để chọn chiến lược

| Tình huống | Cách tiếp cận thường phù hợp |
| --- | --- |
| Chỉ refactor logic, biểu diễn không đổi | Giữ hợp đồng, kiểm tra các trường hợp biên và regression |
| Bổ sung cách đọc format mới nhưng chưa ghi | Expand reader trước, duy trì writer cũ |
| Đổi biểu diễn có ánh xạ hai chiều chính xác | Reader tương thích, migration và điều phối writer |
| Đổi biểu diễn làm mất thông tin | Xác nhận nghiệp vụ, lưu bản gốc hoặc kế hoạch chuyển đổi không thể đảo ngược |
| Đổi kiểu cột lớn hoặc không thể hỗ trợ cả hai trong một cột | Cân nhắc thêm cột mới, dual write/backfill |
| Rolling deployment nhiều instance | Đánh giá ma trận reader/writer và rollback |
| Có consumer ngoài hệ thống Java | Xem định dạng lưu trữ là hợp đồng tích hợp, cần phối hợp nâng cấp |
| Có dữ liệu lịch sử không rõ version | Khảo sát phân bố, bổ sung version/metadata nếu cần |
| Converter có `autoApply` | Liệt kê mọi field/bảng chịu ảnh hưởng |
| Query phụ thuộc giá trị vật lý | Sửa/query tạm thời, backfill và xác nhận kết quả |
| Đổi mã hóa/serialization | Giữ metadata version, khả năng đọc lịch sử và phương án phục hồi |

Không nên chọn migration tại chỗ chỉ vì dễ viết SQL, cũng không nên áp dụng dual write kéo dài nếu không có yêu cầu. Quyết định cần dựa trên tính đúng dữ liệu, mô hình triển khai và khả năng quan sát thực tế.

## 24. Một kế hoạch thay đổi có thể trình bày cho nhóm phát triển

Giả sử mục tiêu là chuyển `state_code` từ một ký tự sang tên đầy đủ. Một kế hoạch đủ rõ cho reviewer nên có các nội dung sau.

### 24.1. Hợp đồng cũ và mới

```text
OLD:
  NEW       <-> "N"
  SHIPPED   <-> "S"
  DELIVERED <-> "D"

NEW:
  NEW       <-> "NEW"
  SHIPPED   <-> "SHIPPED"
  DELIVERED <-> "DELIVERED"
```

Ghi rõ định nghĩa `null`, mã lạ, điều kiện toàn vẹn và tất cả bảng/cột áp dụng.

### 24.2. Trạng thái dữ liệu

Ví dụ kết quả kiểm tra:

```text
N: 12,540 rows
S:  4,860 rows
D:  7,620 rows
other: 15 rows
```

Phải xử lý nhóm `other` trước khi tuyên bố migration có thể hoàn thành hoàn toàn. Nếu cần, lập quy tắc phân loại bằng nghiệp vụ thay vì tự thay thành `NEW`.

### 24.3. Trình tự triển khai

1. **Schema:** mở rộng cột và các constraint cần thiết.
2. **Code đọc:** triển khai bộ giải mã chấp nhận cả cũ và mới; phía ghi vẫn cũ.
3. **Consumer:** nâng cấp tất cả node, job và tích hợp cần đọc mã mới.
4. **Code ghi:** chuyển writer sang tên đầy đủ sau khi xác nhận không còn reader cũ.
5. **Backfill:** chuyển các hàng cũ theo mapping được phê duyệt và theo dõi mã cũ có còn phát sinh không.
6. **Verification:** so sánh số bản ghi, truy vấn, kết quả nghiệp vụ và metric.
7. **Contract:** thu hẹp constraint/decoder và xóa code chuyển tiếp khi an toàn.

### 24.4. Tiêu chí chấp nhận

Ví dụ:

- Mọi bản ghi trước migration đều được đọc thành đúng `OrderState` hoặc được cách ly xử lý nếu có mã bất thường.
- Không còn writer ghi `N/S/D` sau điểm chuyển đổi đã xác nhận.
- Các query nghiệp vụ không bỏ sót bản ghi do tồn tại hai biểu diễn.
- Bảng và index phục vụ workload vẫn đáp ứng giới hạn hiệu năng.
- Có phương án rollback hoặc chiến lược xử lý sự cố phù hợp với thời điểm bắt đầu ghi format mới.
- Backup/restore và job nền vẫn đọc được dữ liệu theo version cần hỗ trợ.

### 24.5. Chỉ số theo dõi

Trong giai đoạn chuyển tiếp, có thể theo dõi:

- Số bản ghi còn mã cũ.
- Tỷ lệ lỗi decode/unknown code.
- Số thao tác ghi mã cũ sau khi đã switch writer.
- Số kết quả truy vấn khác biệt giữa logic cũ và logic mới.
- Lỗi constraint và transaction rollback.
- Thời gian, lock, replication lag, độ trễ query trong lúc backfill.

Nếu không có tín hiệu quan sát, khó xác định quá trình chuyển đổi đã đủ điều kiện để bỏ format cũ hay chưa.

## 25. Bài tập suy luận

### Bài tập 1: Đổi mã enum có còn tương thích?

Converter v1:

```text
ACTIVE  -> "A"
BLOCKED -> "B"
```

Converter v2:

```text
ACTIVE  -> "ACTIVE"
BLOCKED -> "BLOCKED"
```

**Câu hỏi:** Nếu deploy trực tiếp v2 vào database còn `"A"` và `"B"`, rủi ro là gì?

**Gợi ý:** Code có thể biên dịch nhưng converter đọc không nhận diện mã cũ; cột quá ngắn; bản v1 không hiểu dữ liệu v2; SQL và báo cáo còn phụ thuộc mã cũ.

### Bài tập 2: Converter đọc được cả hai nhưng query bị thiếu

Database có:

| id | state_code |
| ---: | --- |
| 1 | S |
| 2 | SHIPPED |

Converter đọc `"S"` và `"SHIPPED"` đều thành `OrderState.SHIPPED`, nhưng `convertToDatabaseColumn(SHIPPED)` chỉ trả `"SHIPPED"`.

**Câu hỏi:** Một JPQL query `WHERE o.state = :state` với tham số `SHIPPED` có chắc trả cả hai hàng không?

**Đáp án:** Không. Giá trị tham số thường được chuyển thành một biểu diễn SQL duy nhất. Cần kế hoạch truy vấn cho mixed-format hoặc backfill để chuẩn hóa dữ liệu.

### Bài tập 3: Đổi đơn vị lưu trữ

Database cũ lưu số milliseconds từ epoch; converter mới hiểu cùng một cột là seconds từ epoch. Cả hai vẫn dùng `BIGINT`.

**Câu hỏi:** Vì sao chỉ kiểm tra schema và compile không thể phát hiện lỗi?

**Đáp án:** Kiểu dữ liệu không thay đổi nhưng **đơn vị và ý nghĩa** đã thay đổi. Cần migration hoặc versioned interpretation; nếu không giá trị thời điểm sẽ bị diễn giải sai hàng nghìn lần.

### Bài tập 4: Rolling deploy

Hiện còn ba instance v1 chỉ đọc `N/S/D`. Đã deploy một instance v2 đọc cả cũ/mới.

**Câu hỏi:** Có nên bật writer ghi `NEW/SHIPPED/DELIVERED` trên instance v2 ngay không?

**Đáp án:** Chưa nên, nếu các instance v1 còn có thể đọc những hàng được v2 cập nhật. Trước tiên cần nâng cấp các reader liên quan và xác định chiến lược rollback an toàn.

### Bài tập 5: Converter làm mất thông tin

Converter mới chuẩn hóa mọi mã khách hàng sang uppercase. Dữ liệu cũ có `"ab-01"` và `"AB-01"` là hai khách hàng khác nhau.

**Câu hỏi:** Đây là vấn đề về parse, schema hay nghiệp vụ?

**Đáp án:** Cả ba có thể liên quan, nhưng rủi ro lớn nhất là **mất phân biệt identity nghiệp vụ**. Hai giá trị khác nhau bị gộp; unique key và logic tra cứu có thể xung đột. Không thể giải quyết an toàn chỉ bằng thay method Java.

## 26. Những sai lầm thường gặp

**“Converter mới chạy được với dữ liệu mới là đủ.”** Chưa đủ: cần thử dữ liệu lịch sử được ghi bằng các version trước.

**“Giữ nguyên generic type `AttributeConverter<X, Y>` tức là tương thích.”** Kiểu có thể giữ nguyên nhưng mã, đơn vị, precision hoặc ý nghĩa đã thay đổi.

**“Đọc được cả hai định dạng thì query sẽ tìm được cả hai.”** Không chắc: điều kiện equality có thể chuyển tham số thành đúng một format vật lý.

**“Rolling deployment chỉ cần server mới đọc được dữ liệu cũ.”** Bản server cũ cũng có thể phải đọc dữ liệu do server mới ghi.

**“Rollback code đồng nghĩa rollback đầy đủ.”** Dữ liệu đã ghi theo format mới vẫn tồn tại sau khi đổi lại binary.

**“Có constraint trong schema là tránh được mọi lỗi.”** Constraint thường xác nhận định dạng/tập giá trị, không bảo đảm mã `"S"` vẫn được hiểu đúng sau khi đổi nghĩa.

**“Không cần xét native SQL nếu entity dùng converter.”** Native SQL, job trực tiếp, CDC và báo cáo có thể bỏ qua converter hoàn toàn.

**“Gặp mã lạ cứ trả null.”** Cách đó có thể che giấu dữ liệu lỗi và làm mất khả năng chẩn đoán.

**“Migration đã chạy xong nên xóa ngay decoder cũ.”** Cần xác nhận không còn writer cũ, backup hoặc payload lịch sử nào yêu cầu decoder đó.

**“Số bản ghi trước và sau giống nhau tức là thành công.”** Dữ liệu có thể bị đổi đơn vị, gộp giá trị hoặc đọc sai ý nghĩa mà không mất hàng nào.

## 27. Cách tư duy khi review thay đổi converter

Khi xem một pull request sửa `AttributeConverter` hoặc quy tắc ánh xạ kiểu giá trị, có thể đọc theo thứ tự sau:

1. **Thay đổi đầu vào/đầu ra:** ghi rõ ví dụ `Java → DB` và `DB → Java` trước và sau.
2. **Xác định dữ liệu lịch sử:** hàng hiện có được ghi dưới những quy tắc nào, có phiên bản/metadata gì?
3. **Đánh giá bảo toàn ý nghĩa:** round-trip có mất thông tin, đổi đơn vị hoặc gộp giá trị không?
4. **Đánh giá chiều đọc cũ/mới:** reader mới có hiểu định dạng cũ; reader cũ có gặp dữ liệu mới trong triển khai không?
5. **Kiểm tra schema:** type, length, nullability, index, unique, CHECK, foreign key.
6. **Kiểm tra truy vấn và hệ thống phụ thuộc:** JPQL, native SQL, report, job, data pipeline, cache.
7. **Thiết kế chuyển tiếp:** mở rộng reader/schema trước khi đổi writer; migration có khả năng quan sát.
8. **Xác định rollback:** khi nào được phép rollback, khi nào phải tiến về phía trước?
9. **Xác định điều kiện kết thúc:** khi nào chắc chắn bỏ được mã cũ và xóa logic tương thích?
10. **Lưu lại hợp đồng mới:** để lần nâng cấp tiếp theo không lặp lại sai lầm tương tự.

Đây là cách kết nối kiến thức **kiểu giá trị** với các chủ đề lớn của JPA như ánh xạ thuộc tính, quản lý schema, truy vấn, transaction và lifecycle của ứng dụng.

## Kết luận

Một quy tắc chuyển đổi trong ORM/JPA là **hợp đồng giữa giá trị miền nghiệp vụ và dữ liệu tồn tại lâu dài trong database**. Khi đổi quy tắc, cần đánh giá khả năng đọc dữ liệu cũ, bảo toàn ý nghĩa, ghi dữ liệu mới, tương thích với phiên bản ứng dụng còn chạy, tác động tới schema/query/cache và khả năng rollback.

Điểm khó không nằm ở việc viết thêm vài nhánh trong `AttributeConverter`, mà ở việc hệ thống có thể tồn tại **nhiều định dạng dữ liệu và nhiều phiên bản ứng dụng cùng lúc**. Một converter đọc được cả hai format có thể vẫn khiến query bỏ sót dữ liệu; một thay đổi giữ nguyên kiểu Java và SQL có thể vẫn làm sai đơn vị hoặc nghĩa nghiệp vụ.

Khi sửa converter, hãy luôn bắt đầu từ câu hỏi: **“Giá trị nào đã nằm trong database từ trước, ai đang đọc/ghi nó, và mỗi phiên bản sẽ hiểu giá trị ấy như thế nào trong suốt quá trình chuyển đổi?”**. Trả lời được câu hỏi đó, rồi thiết kế migration và kiểm chứng phù hợp, sẽ giúp thay đổi kiểu giá trị mà không đánh đổi tính toàn vẹn của dữ liệu.
