# Enum, bảng danh mục và miền giá trị có thể mở rộng

Nhiều thuộc tính dữ liệu chỉ nhận giá trị từ một tập hợp xác định. Trạng thái đơn hàng có thể là `PENDING`, `CONFIRMED` hoặc `CANCELLED`; phương thức giao hàng có thể là giao tiêu chuẩn, giao nhanh hoặc nhận tại cửa hàng. Tập giá trị này cần được kiểm soát để tránh dữ liệu sai chính tả, sai quy ước hoặc không còn được hệ thống hiểu.

Có nhiều cách biểu diễn tập giá trị: enum trong mã nguồn, kiểu enum của DBMS, `CHECK` constraint hoặc bảng danh mục (lookup/reference table). Mỗi cách có chi phí và khả năng tiến hóa khác nhau. Một tập giá trị cố định trong vòng đời ứng dụng có thể phù hợp với enum; một danh mục do nghiệp vụ quản trị, thường xuyên thêm hoặc ngừng sử dụng giá trị, thường cần dữ liệu tham chiếu có thể mở rộng.

Trong phạm vi **DATABASE_DATA_MODELING**, bài học phân biệt tập giá trị đóng và miền giá trị mở rộng, chỉ ra cách chọn cấu trúc, bảo vệ toàn vẹn dữ liệu và thay đổi danh mục mà không làm hỏng dữ liệu cũ hoặc consumer.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt enum trong ngôn ngữ lập trình, enum của DBMS, `CHECK` constraint và bảng danh mục.
- Nhận biết khi nào một miền giá trị nên đóng, khi nào cần mở rộng theo dữ liệu hoặc cấu hình.
- Thiết kế mã giá trị ổn định, nhãn hiển thị, trạng thái hoạt động và khóa ngoại phù hợp.
- Chọn cách xử lý giá trị đã ngừng sử dụng, giá trị chưa biết và giá trị mới từ hệ thống bên ngoài.
- Lập kế hoạch migration, seed dữ liệu, version hợp đồng và kiểm thử khi miền giá trị thay đổi.

## 1. Miền giá trị là gì?

**Miền giá trị (value domain)** xác định tập các giá trị hợp lệ mà một thuộc tính có thể nhận. Miền có thể được mô tả bằng kiểu dữ liệu, phạm vi số, mẫu định dạng, tập giá trị liệt kê hoặc một tập bản ghi tham chiếu.

Ví dụ:

| Thuộc tính | Miền giá trị | Quy tắc ví dụ |
|---|---|---|
| `quantity` | Số nguyên dương | `quantity >= 1` |
| `currency_code` | Mã tiền tệ được hỗ trợ | Phải thuộc danh mục tiền tệ hợp lệ |
| `order_status` | Tập trạng thái đơn hàng | `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED` |
| `delivery_method` | Phương thức giao nhận | `STANDARD`, `EXPRESS`, `PICKUP` và các phương thức được bổ sung |
| `customer_type` | Phân loại khách hàng | `PERSON`, `ORGANIZATION` nếu miền được quy định đóng |

Miền giá trị giúp nhiều thành phần hiểu cùng một dữ liệu theo cùng một quy tắc. Nếu một thuộc tính được mô tả là trạng thái đơn hàng nhưng hệ thống chấp nhận tùy ý chuỗi như `done`, `finish`, `completed` hoặc `complete`, việc lọc, thống kê và xử lý nghiệp vụ sẽ trở nên không nhất quán.

### 1.1. Tập giá trị đóng và miền giá trị mở rộng

- **Tập giá trị đóng (closed set):** danh sách giá trị được xác định bởi thiết kế và chỉ thay đổi khi có thay đổi phần mềm hoặc schema được kiểm soát. Ví dụ trạng thái nội bộ có chuyển đổi nghiệp vụ cố định.
- **Miền giá trị mở rộng (extensible domain):** danh sách có thể được bổ sung, vô hiệu hóa hoặc cấu hình theo tổ chức, thị trường hay thời gian mà không nhất thiết phải sửa mã nguồn và triển khai ứng dụng cho mỗi giá trị mới.

Đóng hay mở là thuộc tính của quy trình quản trị miền, không chỉ là tính năng của công cụ lưu trữ. Một bảng danh mục có thể được quản trị rất chặt và gần như đóng; một enum trong mã nguồn có thể được cập nhật thường xuyên qua release. Câu hỏi cần trả lời là ai có quyền thay đổi, thay đổi diễn ra bằng cách nào và các consumer phản ứng ra sao.

### 1.2. Phân biệt giá trị, mã và nhãn hiển thị

Một giá trị nên có mã ổn định và nhãn hiển thị riêng.

| Thành phần | Ví dụ | Mục đích |
|---|---|---|
| Code | `EXPRESS` | Lưu trữ, tích hợp và so sánh ổn định |
| Label | `Giao nhanh` | Hiển thị cho người dùng |
| Description | `Giao trong khung thời gian ưu tiên` | Giải thích ý nghĩa |
| Sort order | `20` | Sắp xếp trong giao diện hoặc báo cáo |
| Active flag | `true` | Cho biết có thể chọn giá trị mới hay không |

Không dùng nhãn hiển thị làm mã lưu trữ. Nhãn có thể thay đổi cách viết, dịch sang ngôn ngữ khác hoặc điều chỉnh theo giao diện. Nếu lưu `Giao nhanh` trong mọi bảng giao dịch, việc đổi nhãn thành `Giao hỏa tốc` sẽ đòi hỏi sửa dữ liệu và có thể làm hỏng tích hợp. Lưu `EXPRESS` giúp nhãn thay đổi mà ý nghĩa định danh vẫn ổn định.

## 2. Enum trong mã nguồn

Enum của ngôn ngữ lập trình biểu diễn một tập hằng số có tên. Nó giúp compiler và IDE phát hiện giá trị không hợp lệ, làm rõ các nhánh xử lý và tránh dùng chuỗi tự do trong logic.

Ví dụ Java:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

Sử dụng enum:

```java
public boolean canShip(OrderStatus status) {
    return status == OrderStatus.CONFIRMED;
}
```

### 2.1. Ưu điểm

- Tập giá trị được thể hiện rõ trong mã nguồn.
- Compiler phát hiện nhiều lỗi đánh máy hoặc nhánh xử lý thiếu.
- Có thể gắn hành vi, thuộc tính hoặc phương thức vào từng giá trị khi phù hợp.
- Dễ tìm kiếm và refactor trong IDE.
- Phù hợp với tập giá trị ít thay đổi và thuộc quyền kiểm soát của nhóm phát triển.

### 2.2. Giới hạn khi miền cần mở rộng

Khi thêm một hằng số vào enum, ứng dụng thường cần biên dịch và triển khai lại. Nếu một bộ phận nghiệp vụ cần tự thêm phương thức giao hàng hoặc loại khách hàng mà không chờ release, enum thuần trong mã nguồn không đáp ứng tốt yêu cầu đó.

Enum cũng có thể gây vấn đề khi đọc dữ liệu mới hơn phiên bản ứng dụng. Ví dụ database hoặc một service khác đã ghi `RETURNED`, nhưng instance cũ chỉ biết `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED`. Việc parse enum có thể ném lỗi hoặc làm message bị từ chối.

### 2.3. Lưu enum vào database: dùng tên, không dùng ordinal

Nếu lưu enum Java vào cột số theo vị trí (`ORDINAL`), việc chèn hoặc sắp xếp lại hằng số có thể làm dữ liệu cũ mang ý nghĩa khác. Ví dụ giá trị `1` ban đầu là `CONFIRMED`, nhưng sau khi thêm một hằng số lên đầu danh sách, `1` có thể được giải nghĩa thành trạng thái khác.

Nếu dùng enum trong mã nguồn với JPA, thường nên lưu tên ổn định:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 20)
private OrderStatus status;
```

Tên enum cũng là một phần hợp đồng dữ liệu. Đổi tên hằng số có thể khiến ứng dụng không đọc được các hàng đã lưu bằng tên cũ. Nếu cần đổi cách đặt tên, hãy cân nhắc giữ code lưu trữ ổn định và ánh xạ code sang enum, hoặc thực hiện migration có kiểm soát.

## 3. Enum của DBMS và CHECK constraint

Một số hệ quản trị cơ sở dữ liệu hỗ trợ kiểu enum riêng. PostgreSQL cho phép tạo kiểu enum:

```sql
CREATE TYPE order_status AS ENUM (
    'PENDING',
    'CONFIRMED',
    'SHIPPED',
    'CANCELLED'
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status order_status NOT NULL DEFAULT 'PENDING'
);
```

DBMS kiểm tra giá trị ngay tại nơi ghi dữ liệu. Điều này hữu ích khi nhiều ứng dụng cùng ghi vào một schema và cần bảo vệ tập giá trị ở tầng database.

### 3.1. Ưu điểm và giới hạn của DBMS enum

Ưu điểm:

- Giá trị không hợp lệ bị từ chối bởi database.
- Cột thể hiện rõ miền giá trị ở mức schema.
- Có thể dùng cùng một kiểu cho nhiều bảng nếu ý nghĩa thực sự giống nhau.

Giới hạn:

- Khả năng thay đổi và xóa giá trị phụ thuộc DBMS; một số thay đổi cần migration đặc biệt.
- Enum gắn với schema và công cụ của một DBMS, giảm tính di động.
- Không thuận tiện khi giá trị có metadata như nhãn đa ngôn ngữ, thứ tự, mô tả, ngày hiệu lực hoặc cấu hình theo tenant.
- Nếu danh mục do người dùng quản trị, việc mỗi lần thêm giá trị phải thay đổi schema là không phù hợp.

### 3.2. CHECK constraint

Với một tập giá trị nhỏ và ổn định, `CHECK` là lựa chọn đơn giản:

```sql
CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('PENDING', 'CONFIRMED', 'SHIPPED', 'CANCELLED'))
);
```

`CHECK` phù hợp với miền đóng và các điều kiện đơn giản như số lượng dương, phần trăm từ 0 đến 100 hoặc trạng thái thuộc một danh sách nhỏ.

Khi thêm một trạng thái mới, constraint phải được cập nhật bằng migration. Với bảng lớn hoặc hệ thống cần triển khai không gián đoạn, cần tính đến thứ tự thay đổi giữa schema và ứng dụng: database phải chấp nhận giá trị mới trước khi phiên bản ứng dụng ghi giá trị đó.

### 3.3. CHECK không thay thế state machine

Constraint kiểm tra một giá trị có thuộc miền hợp lệ hay không. Nó không tự kiểm tra một chuyển đổi trạng thái có hợp lệ trong ngữ cảnh hay không.

Ví dụ, cả `PENDING`, `CONFIRMED`, `SHIPPED` và `CANCELLED` đều là giá trị hợp lệ. Nhưng quy tắc nghiệp vụ có thể chỉ cho phép:

- `PENDING` → `CONFIRMED` hoặc `CANCELLED`.
- `CONFIRMED` → `SHIPPED` hoặc `CANCELLED`.
- `SHIPPED` không thể quay về `PENDING`.

Để bảo vệ chuyển đổi, cần logic nghiệp vụ, transaction, optimistic locking hoặc một cơ chế kiểm soát tương ứng. Việc giá trị nằm trong enum hoặc bảng danh mục không có nghĩa mọi chuyển đổi giữa chúng đều hợp lệ.

## 4. Bảng danh mục (Lookup / Reference Table)

Bảng danh mục lưu mỗi giá trị hợp lệ thành một bản ghi riêng. Các bảng nghiệp vụ tham chiếu mã danh mục bằng khóa ngoại.

Ví dụ bảng phương thức giao hàng:

```sql
CREATE TABLE delivery_method (
    delivery_method_code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO delivery_method
    (delivery_method_code, display_name, sort_order)
VALUES
    ('STANDARD', 'Giao tiêu chuẩn', 10),
    ('EXPRESS', 'Giao nhanh', 20),
    ('PICKUP', 'Nhận tại cửa hàng', 30);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    delivery_method_code VARCHAR(30) NOT NULL
        REFERENCES delivery_method(delivery_method_code)
);
```

Khi thêm phương thức mới, có thể thêm một hàng vào `delivery_method` mà không thay đổi cấu trúc bảng `sales_order`. Khóa ngoại bảo đảm mọi đơn hàng tham chiếu đến một mã đã tồn tại.

### 4.1. Ưu điểm

- Có thể thêm giá trị bằng thao tác dữ liệu có kiểm soát, không cần thay schema cho mỗi giá trị mới.
- Lưu được metadata: nhãn, mô tả, thứ tự hiển thị, nhóm, ngày hiệu lực, trạng thái hoạt động và nguồn quản lý.
- Có thể hỗ trợ nhãn đa ngôn ngữ bằng bảng dịch riêng.
- Khóa ngoại bảo vệ tính toàn vẹn tham chiếu.
- Phù hợp với danh mục do nghiệp vụ, quản trị viên hoặc tenant cấu hình.

### 4.2. Chi phí và rủi ro

- Cần quản trị vòng đời danh mục, quyền thêm/sửa/ngừng sử dụng và quy trình phê duyệt.
- Có thể cần join hoặc cache khi đọc nhãn hiển thị.
- Nếu code danh mục bị đổi hoặc tái sử dụng, dữ liệu lịch sử có thể bị diễn giải sai.
- Thêm giá trị vào bảng không bảo đảm mọi ứng dụng biết cách xử lý giá trị mới.
- Nếu danh mục thay đổi theo tenant hoặc thời gian, cần đưa phạm vi và hiệu lực vào khóa/ràng buộc.

### 4.3. Code ổn định, nhãn có thể đổi

Nên xem `delivery_method_code` là mã ổn định sau khi được công bố. Nếu cần đổi tên hiển thị, chỉ cập nhật `display_name` hoặc bản dịch. Không tái sử dụng code cũ cho một ý nghĩa khác.

Nếu `EXPRESS` ngừng cung cấp, đánh dấu `is_active = FALSE` để ngăn chọn mới. Các đơn hàng cũ vẫn giữ mã `EXPRESS` và vẫn join được đến danh mục để hiển thị lịch sử. Xóa cứng hàng danh mục sẽ làm vi phạm khóa ngoại hoặc khiến dữ liệu lịch sử mất ý nghĩa.

Khóa ngoại chỉ xác nhận code có tồn tại; nó không kiểm tra `is_active` hay ngày hiệu lực. Khi tạo giao dịch mới, ứng dụng cần kiểm tra giá trị đang được phép chọn trong cùng transaction hoặc dùng cơ chế database phù hợp nếu có nhiều đường ghi. Ngược lại, khi đọc giao dịch cũ, vẫn cần cho phép hiển thị giá trị đã ngừng sử dụng. Nếu chứng từ phải giữ nguyên nhãn tại thời điểm phát hành, hãy lưu snapshot nhãn hoặc phiên bản danh mục trên chứng từ; join đến nhãn hiện tại có thể hiển thị tên mới.

### 4.4. Danh mục đa ngôn ngữ

Nếu cần hiển thị nhãn theo ngôn ngữ, không nên tạo một cột cho từng ngôn ngữ trong bảng chính khi số ngôn ngữ có thể tăng. Có thể tách bảng dịch:

```sql
CREATE TABLE delivery_method_translation (
    delivery_method_code VARCHAR(30) NOT NULL
        REFERENCES delivery_method(delivery_method_code),
    locale VARCHAR(10) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    PRIMARY KEY (delivery_method_code, locale)
);
```

Code giữ nguyên cho tích hợp và lưu trữ; `locale` quyết định nhãn hiển thị. Cần xác định fallback khi thiếu bản dịch, ví dụ dùng ngôn ngữ mặc định của hệ thống.

## 5. Miền giá trị mở rộng và quy tắc quản trị

Một danh mục được gọi là mở rộng khi giá trị mới có thể được bổ sung theo quy trình được định nghĩa mà không cần sửa mọi consumer cùng lúc. Để làm được điều đó, cần quản trị nhiều hơn một bảng.

### 5.1. Ai được thêm giá trị?

Xác định chủ thể chịu trách nhiệm cho danh mục:

- Nhóm phát triển quản lý danh mục kỹ thuật, ít thay đổi.
- Nhóm nghiệp vụ quản lý danh mục sản phẩm, phương thức giao nhận hoặc lý do hoàn tiền.
- Quản trị viên tenant quản lý giá trị riêng cho từng tổ chức.
- Hệ thống bên ngoài cung cấp mã; hệ thống nội bộ lưu mã nguồn và ánh xạ sang mã chuẩn.

Quyền quản lý cần gắn với quy trình phê duyệt, audit và kiểm tra xung đột. Không nên cho phép mọi người dùng tự tạo code tùy ý nếu code đó ảnh hưởng báo cáo, định tuyến hoặc logic thanh toán.

### 5.2. Mã danh mục cần có quy tắc

Một code nên:

- Duy nhất trong namespace đã xác định.
- Ổn định sau khi được sử dụng trong giao dịch hoặc tích hợp.
- Không phụ thuộc ngôn ngữ hiển thị.
- Không tái sử dụng cho ý nghĩa khác sau khi ngừng hoạt động.
- Có quy tắc chữ hoa/thường, khoảng trắng và ký tự được phép.
- Có chính sách đồng bộ nếu được cấp bởi hệ thống ngoài.

Ví dụ, `EXPRESS` và `express` không nên vô tình trở thành hai giá trị khác nhau chỉ vì collation hoặc cách so sánh chuỗi. Hãy chuẩn hóa code ở biên nhận dữ liệu và dùng constraint phù hợp.

### 5.3. Ngừng sử dụng thay vì xóa

Các cột thường hữu ích trong danh mục:

| Cột | Ý nghĩa |
|---|---|
| `code` | Mã ổn định được tham chiếu |
| `display_name` | Nhãn mặc định |
| `description` | Mô tả ý nghĩa |
| `is_active` | Có được chọn cho giao dịch mới không |
| `valid_from`, `valid_to` | Khoảng thời gian giá trị có hiệu lực |
| `sort_order` | Thứ tự hiển thị |
| `source` | Nguồn cấp hoặc nguồn quản lý |
| `created_at`, `updated_at` | Dấu thời gian quản trị |

`is_active = FALSE` không có nghĩa mọi bản ghi lịch sử tham chiếu giá trị đó đều không hợp lệ. Nó thường chỉ ngăn tạo mới. Nếu một giá trị chỉ có hiệu lực trong khoảng thời gian, hãy phân biệt thời điểm giao dịch với thời điểm hiện tại khi kiểm tra.

### 5.4. Giá trị toàn cục và giá trị theo tenant

Nếu mỗi tenant có danh mục riêng, cần xác định code duy nhất toàn cục hay trong từng tenant.

```sql
CREATE TABLE tenant_delivery_method (
    tenant_id UUID NOT NULL,
    code VARCHAR(30) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, code)
);
```

Khóa chính `(tenant_id, code)` cho phép hai tenant dùng cùng code với nhãn hoặc chính sách khác nhau. Bảng giao dịch cần lưu `tenant_id` cùng `delivery_method_code` và dùng khóa ngoại ghép để không thể tham chiếu phương thức của tenant khác.

## 6. Giá trị chưa biết, không áp dụng và giá trị khác

Các trường hợp sau có ý nghĩa khác nhau và không nên gộp thành một chuỗi `UNKNOWN`:

- **NULL:** chưa có giá trị hoặc chưa biết theo ngữ nghĩa của cột.
- **NOT_APPLICABLE:** thuộc tính không áp dụng cho bản ghi đó.
- **UNKNOWN:** đã cần một giá trị nhưng chưa xác định được.
- **OTHER:** giá trị có tồn tại nhưng không nằm trong các lựa chọn cụ thể đã liệt kê.
- **UNSPECIFIED:** producer không cung cấp thông tin; khác với việc hệ thống đã xác minh là chưa biết.

Không phải miền nào cũng cần mọi trạng thái trên. Hãy xác định ý nghĩa nghiệp vụ và cách báo cáo trước khi thêm chúng. Nếu dùng `OTHER`, có thể cần thêm trường mô tả để ghi nhận giá trị cụ thể; nếu không, thông tin sẽ bị mất.

Với tích hợp bên ngoài, không nên tự động chuyển mọi code không nhận diện thành `OTHER` nếu điều đó làm sai nghĩa. Có thể lưu raw code, đánh dấu chưa ánh xạ và đưa vào hàng chờ xử lý để cập nhật danh mục hoặc mapping.

## 7. Mô hình lai: enum trong code kết hợp bảng danh mục

Một số miền cần cả hai đặc tính: logic cốt lõi cần type safety, nhưng nhãn hoặc cấu hình cần được quản trị bằng dữ liệu. Có thể dùng mô hình lai, nhưng phải hiểu rõ giới hạn.

Ví dụ với trạng thái đơn hàng:

- Java enum định nghĩa các trạng thái mà ứng dụng biết và có hành vi tương ứng.
- Bảng `order_status_catalog` lưu code, nhãn, thứ tự và trạng thái hoạt động.
- Database constraint hoặc khóa ngoại bảo đảm code được phép lưu.
- Khi thêm trạng thái mới, cần cập nhật cả danh mục và ứng dụng nếu logic xử lý phụ thuộc vào enum.

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

```sql
CREATE TABLE order_status_catalog (
    code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status_code VARCHAR(20) NOT NULL
        REFERENCES order_status_catalog(code)
);
```

Mô hình này phù hợp khi tập trạng thái được kiểm soát bởi release phần mềm nhưng nhãn, thứ tự hiển thị hoặc trạng thái được phép chọn cần cấu hình. Nó không biến trạng thái thành miền tự do mở rộng: nếu thêm `RETURNED` mà code ứng dụng không biết phải xử lý chuyển trạng thái, hoàn tiền hoặc tồn kho ra sao, chỉ thêm một hàng danh mục là chưa đủ.

Nếu cần cho phép giá trị mới mà không triển khai ứng dụng, hãy dùng code dạng value object/string có validation theo danh mục và thiết kế consumer có khả năng xử lý giá trị chưa biết. Chỉ nên làm vậy khi nghiệp vụ thực sự cho phép consumer xử lý tổng quát mà không cần logic riêng cho từng giá trị.

## 8. So sánh các cách biểu diễn

| Cách biểu diễn | Kiểm tra giá trị ở đâu? | Thêm giá trị mới | Metadata và quản trị | Phù hợp khi |
|---|---|---|---|---|
| Enum trong mã nguồn | Compiler và ứng dụng | Thường cần release ứng dụng | Có thể gắn metadata trong code; khó cho nghiệp vụ tự quản trị | Tập nhỏ, đóng, logic xử lý gắn với từng giá trị |
| Enum của DBMS | Database | Cần migration schema; mức độ linh hoạt tùy DBMS | Hạn chế metadata ngoài tên giá trị | Tập đóng cần DBMS bảo vệ trực tiếp |
| `CHECK` constraint | Database | Cập nhật constraint bằng migration | Không thuận tiện cho nhãn, dịch và quản trị dữ liệu | Tập nhỏ, ổn định hoặc điều kiện miền đơn giản |
| Lookup/reference table | Khóa ngoại và dữ liệu danh mục | Thêm bản ghi danh mục | Tốt cho nhãn, mô tả, hiệu lực, tenant và audit | Danh mục có thể mở rộng hoặc có metadata |
| Mô hình lai | Ứng dụng và database | Có thể cần cập nhật cả code lẫn danh mục | Kết hợp type safety và metadata | Logic cốt lõi cố định, metadata cần cấu hình |

Không có một cách biểu diễn tốt nhất cho mọi thuộc tính. Một hệ thống có thể dùng enum cho trạng thái nội bộ, lookup table cho phương thức giao hàng và `CHECK` cho số lượng dương.

## 9. Quy trình thay đổi miền giá trị

Thêm, đổi hoặc ngừng một giá trị có thể ảnh hưởng dữ liệu, ứng dụng, API, event, báo cáo và tích hợp. Hãy quản lý như một thay đổi hợp đồng dữ liệu.

### 9.1. Thêm giá trị mới

Với miền dùng lookup table:

1. Xác định code, ý nghĩa, nguồn cấp, phạm vi và ngày hiệu lực.
2. Kiểm tra code chưa tồn tại và không xung đột với namespace khác.
3. Thêm bản ghi danh mục qua migration/seed hoặc quy trình quản trị được phân quyền.
4. Cập nhật ứng dụng và consumer nếu giá trị mới cần logic xử lý riêng.
5. Cập nhật API/event schema hoặc tài liệu nếu code được công bố ra ngoài.
6. Kiểm thử dữ liệu mới, dữ liệu cũ và consumer phiên bản cũ.

Với enum hoặc `CHECK`, database cần chấp nhận giá trị mới trước khi ứng dụng bắt đầu ghi giá trị đó. Thứ tự triển khai cần tính đến các instance ứng dụng cũ vẫn đang chạy.

### 9.2. Đổi nhãn hoặc mô tả

Nếu chỉ thay đổi cách hiển thị, giữ nguyên code. Cập nhật nhãn, bản dịch hoặc mô tả; kiểm tra cache và các màn hình đang sử dụng. Không cần sửa giao dịch lịch sử nếu ý nghĩa code không đổi.

### 9.3. Ngừng sử dụng giá trị

Thông thường, đánh dấu không hoạt động và ngăn chọn mới. Vẫn cho phép đọc dữ liệu lịch sử. Nếu giá trị cần được thay thế, tạo mapping hoặc quy tắc chuyển đổi có chủ đích; không đổi code cũ thành code mới ngay trong mọi bản ghi nếu hai ý nghĩa không hoàn toàn tương đương.

### 9.4. Thay đổi ý nghĩa

Nếu ý nghĩa nghiệp vụ của một code thay đổi đáng kể, hãy tạo code mới. Tái sử dụng code cũ khiến các bản ghi lịch sử bị diễn giải theo nghĩa mới. Nếu cần hợp nhất hoặc ánh xạ hai code, lưu quan hệ thay thế và ngày hiệu lực.

### 9.5. Đổi tên code

Đổi code có thể ảnh hưởng khóa ngoại, dữ liệu tích hợp và event đã phát. Nếu code đã được công bố, ưu tiên giữ code cũ như alias hoặc mapping trong giai đoạn chuyển tiếp. Nếu bắt buộc đổi, thực hiện migration có thứ tự, cập nhật consumer và lưu lịch sử ánh xạ từ code cũ sang code mới.

## 10. Hợp đồng API và khả năng tương thích

Khi một API trả về:

```json
{
  "orderId": "ord_7305",
  "status": "CONFIRMED"
}
```

`status` là một phần hợp đồng. Consumer có thể dùng switch/case hoặc enum riêng. Khi producer thêm `RETURN_REQUESTED`, consumer cũ có thể:

- Từ chối parse payload vì enum không có giá trị mới.
- Rơi vào nhánh mặc định và xử lý sai.
- Bỏ qua trạng thái mới nhưng vẫn hiển thị đơn hàng.

Producer cần công bố chính sách tương thích. Consumer nên có hành vi với giá trị chưa biết phù hợp với mức rủi ro: từ chối có kiểm soát, lưu raw code, hiển thị trạng thái chung hoặc cách ly message. Không nên mặc định mọi trạng thái mới tương đương `PENDING` hay `OTHER`.

Nếu miền cần mở rộng độc lập với release consumer, contract nên định nghĩa field là code string có danh mục được quản lý và yêu cầu consumer xử lý giá trị chưa biết theo chính sách. Nếu mỗi giá trị có logic nghiệp vụ riêng, việc thêm giá trị vẫn là thay đổi phần mềm và cần phối hợp version.

## 11. Seed dữ liệu, migration và môi trường triển khai

Bảng danh mục thường cần dữ liệu ban đầu. Cần phân biệt:

- **Schema migration:** tạo bảng, khóa ngoại, chỉ mục và constraint.
- **Reference-data seed:** thêm các code chuẩn ban đầu.
- **Runtime administration:** thay đổi danh mục do người có quyền thực hiện sau khi hệ thống chạy.

Seed cần có tính lặp an toàn (idempotent). Chạy lại không tạo bản ghi trùng hoặc ghi đè nhãn đã được quản trị nếu đó không phải chủ đích. Có thể dùng câu lệnh upsert có kiểm soát, nhưng phải quyết định rõ trường nào do code quản lý và trường nào do người dùng quản lý.

Ví dụ PostgreSQL:

```sql
INSERT INTO delivery_method
    (delivery_method_code, display_name, sort_order, is_active)
VALUES
    ('STANDARD', 'Giao tiêu chuẩn', 10, TRUE),
    ('EXPRESS', 'Giao nhanh', 20, TRUE)
ON CONFLICT (delivery_method_code) DO NOTHING;
```

`DO NOTHING` tránh ghi đè dữ liệu danh mục đã được chỉnh sửa. Nếu release cần cập nhật mô tả chuẩn, hãy viết migration riêng nêu rõ các trường được cập nhật và lý do.

Trong triển khai nhiều phiên bản ứng dụng:

1. Triển khai database cho phép code mới.
2. Triển khai ứng dụng có thể đọc cả giá trị cũ và mới.
3. Bật ghi giá trị mới sau khi consumer đã sẵn sàng.
4. Theo dõi lỗi parse, message bị cách ly và số lượng bản ghi theo code.
5. Chỉ loại bỏ hỗ trợ code cũ khi không còn dữ liệu hoặc consumer cần nó.

Với lookup table, bước thêm dữ liệu thường tách biệt khỏi schema migration, nhưng consumer vẫn cần được chuẩn bị nếu giá trị mới có ngữ nghĩa mới.

## 12. Kiểm thử và kiểm soát chất lượng

Một miền giá trị tốt cần kiểm thử ở nhiều lớp:

| Lớp | Kiểm tra |
|---|---|
| Domain/application | Từ chối code không hợp lệ; xử lý đúng từng trạng thái và chuyển đổi được phép |
| Database | `CHECK`, enum hoặc FK từ chối giá trị không tồn tại; không xóa danh mục đang được tham chiếu trái chính sách |
| API/event | Schema validation, giá trị chưa biết, version cũ và mới |
| Migration/seed | Triển khai từ database rỗng và database có dữ liệu; chạy seed lặp an toàn |
| Báo cáo | Nhóm và lọc theo code ổn định; nhãn hiển thị không làm thay đổi phép tổng hợp |
| Vận hành | Cache được làm mới; thay đổi danh mục có audit và quyền phù hợp |

Các ca kiểm thử nên có:

- Ghi một code hợp lệ.
- Ghi code không tồn tại.
- Thêm một code mới và đọc được bằng phiên bản ứng dụng đã chuẩn bị.
- Ngừng code nhưng vẫn đọc được bản ghi lịch sử tham chiếu code đó.
- Đổi nhãn mà không thay đổi code hoặc kết quả tổng hợp.
- Consumer nhận code chưa biết và xử lý theo chính sách.
- Hai người quản trị đồng thời tạo cùng code; unique constraint phải ngăn trùng.
- Seed chạy nhiều lần mà không tạo dữ liệu trùng hoặc ghi đè cấu hình ngoài ý muốn.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng chuỗi tự do cho tập giá trị có quy tắc | Sai chính tả và biến thể code xuất hiện trong dữ liệu | Dùng enum, `CHECK` hoặc bảng danh mục phù hợp |
| Lưu ordinal của enum | Thêm/sắp xếp hằng số làm đổi ý nghĩa dữ liệu cũ | Lưu code/tên ổn định, tránh ordinal |
| Dùng nhãn hiển thị làm code | Đổi nhãn hoặc dịch ngôn ngữ làm thay đổi dữ liệu | Tách code khỏi label |
| Xóa danh mục đang được tham chiếu | Mất lịch sử hoặc vi phạm FK | Đánh dấu inactive; giữ bản ghi danh mục |
| Thêm code vào lookup table nhưng consumer không hiểu | Logic nghiệp vụ không xử lý được giá trị mới | Phối hợp cập nhật consumer hoặc thiết kế xử lý unknown rõ ràng |
| Dùng enum cho danh mục do người dùng tự cấu hình | Mỗi thay đổi nhỏ đều cần release | Dùng reference table có quyền quản trị và audit |
| Dùng lookup table cho trạng thái cần logic cứng nhưng không có kiểm soát chuyển trạng thái | Có thể chuyển trạng thái tùy ý dù code hợp lệ | Xây state machine và kiểm soát transition |
| Tái sử dụng code đã ngừng cho ý nghĩa mới | Dữ liệu lịch sử bị diễn giải sai | Không tái sử dụng code; tạo code mới và mapping khi cần |
| Seed ghi đè nhãn cấu hình | Mất thay đổi do nghiệp vụ quản trị | Phân quyền sở hữu trường và viết migration rõ ràng |

## 14. Quy trình chọn cách biểu diễn

Khi thiết kế một thuộc tính có tập giá trị, hãy tự hỏi:

1. Tập giá trị có đóng và do logic phần mềm quyết định không?
2. Mỗi giá trị có hành vi riêng trong code không?
3. Ai có quyền thêm, đổi nhãn hoặc ngừng giá trị?
4. Có cần mô tả, dịch, sắp xếp, phân nhóm, phạm vi tenant hoặc ngày hiệu lực không?
5. Dữ liệu cũ có cần tiếp tục tham chiếu giá trị đã ngừng không?
6. API/event consumer có thể gặp giá trị mới hơn phiên bản của họ không?
7. Database có cần là hàng rào cuối cùng để từ chối giá trị không hợp lệ không?

Gợi ý lựa chọn:

- Chọn **enum trong mã nguồn** khi tập nhỏ, ổn định và mỗi giá trị gắn với logic riêng.
- Chọn **DBMS enum hoặc CHECK** khi cần database bảo vệ một miền đóng, ít metadata.
- Chọn **lookup/reference table** khi giá trị có thể được thêm hoặc ngừng theo dữ liệu, cần metadata, phân quyền, đa ngôn ngữ hoặc phạm vi tenant.
- Chọn **mô hình lai** khi logic cốt lõi cần type safety nhưng nhãn/cấu hình cần được quản trị bằng dữ liệu. Xác định rõ thêm giá trị có cần release code hay không.

## 15. Checklist thiết kế

- [ ] Miền giá trị và ý nghĩa từng code được định nghĩa rõ.
- [ ] Đã quyết định tập giá trị đóng hay mở rộng và lý do.
- [ ] Code ổn định được tách khỏi nhãn hiển thị và bản dịch.
- [ ] Phạm vi duy nhất của code (toàn cục, issuer, tenant hoặc context) được xác định.
- [ ] Có cơ chế database/application bảo vệ giá trị hợp lệ.
- [ ] Giá trị ngừng sử dụng vẫn hỗ trợ dữ liệu lịch sử.
- [ ] Quy tắc chuyển trạng thái được kiểm soát riêng với kiểm tra miền giá trị.
- [ ] Có chính sách cho NULL, UNKNOWN, OTHER và giá trị chưa biết từ consumer.
- [ ] Seed dữ liệu có thể chạy lặp an toàn và không ghi đè cấu hình ngoài ý muốn.
- [ ] Migration có thứ tự tương thích với các phiên bản ứng dụng đang chạy.
- [ ] API/event công bố cách xử lý khi xuất hiện code mới.
- [ ] Có audit cho thay đổi danh mục và kiểm thử các giá trị cũ, mới, không hợp lệ.

## Tóm tắt

Enum phù hợp với tập giá trị đóng và logic cần type safety. Enum của DBMS và `CHECK` constraint giúp database từ chối giá trị ngoài miền, nhưng mỗi thay đổi thường cần migration schema. Bảng danh mục phù hợp với miền giá trị có thể mở rộng, có metadata hoặc được nghiệp vụ quản trị. Mô hình lai kết hợp enum trong code với bảng danh mục khi logic cốt lõi ổn định nhưng nhãn và cấu hình cần linh hoạt.

Dù chọn cách nào, hãy dùng code ổn định, tách nhãn hiển thị, xác định rõ phạm vi duy nhất và giữ được dữ liệu lịch sử. Việc thêm một giá trị vào danh mục không tự động khiến mọi consumer hiểu giá trị đó; cần quản lý tương thích API/event và logic chuyển đổi riêng.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Value Domain | Tập giá trị hợp lệ mà một thuộc tính có thể nhận |
| Closed Set | Tập giá trị được kiểm soát chặt, thay đổi qua release hoặc migration |
| Extensible Domain | Miền giá trị có thể được bổ sung hoặc cấu hình theo quy trình quản trị |
| Enum | Kiểu liệt kê một tập hằng số có tên |
| CHECK Constraint | Ràng buộc kiểm tra điều kiện trên dữ liệu của một hàng |
| Lookup Table | Bảng lưu các giá trị danh mục để dữ liệu nghiệp vụ tham chiếu |
| Reference Data | Dữ liệu dùng chung để phân loại hoặc chuẩn hóa dữ liệu nghiệp vụ |
| Surrogate Code | Mã ổn định dùng trong lưu trữ/tích hợp, tách khỏi nhãn hiển thị |
| Deprecation | Đánh dấu giá trị không nên dùng mới nhưng vẫn có thể cần đọc dữ liệu cũ |
| State Machine | Mô hình trạng thái và các chuyển đổi hợp lệ giữa chúng |
| Seed Data | Dữ liệu khởi tạo cần có khi triển khai schema hoặc môi trường mới |
| Backward Compatibility | Khả năng phiên bản mới hoặc cũ tiếp tục tương tác theo hợp đồng đã thống nhất |
