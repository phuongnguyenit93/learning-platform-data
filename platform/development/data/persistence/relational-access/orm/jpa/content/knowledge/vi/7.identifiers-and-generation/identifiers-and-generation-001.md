# Lựa chọn khóa nghiệp vụ và khóa thay thế trong JPA

Khi ánh xạ một thực thể Java vào cơ sở dữ liệu quan hệ bằng Jakarta Persistence (JPA), một trong những quyết định nền tảng là **định danh bản ghi bằng giá trị có ý nghĩa nghiệp vụ hay bằng một giá trị do hệ thống tạo ra**. Quyết định này ảnh hưởng đến khóa chính, quan hệ giữa các bảng, cách sinh khóa, khả năng thay đổi dữ liệu, xử lý đồng thời và thiết kế API.

Ví dụ, một sản phẩm có mã `SKU = "BOOK-JPA-001"` và một tài khoản có địa chỉ email `buyer@example.com`. Cả hai giá trị có vẻ dùng để tìm kiếm và phân biệt đối tượng. Nhưng nếu cửa hàng đổi chính sách đặt SKU hoặc khách hàng đổi email, bản ghi cũ có còn là cùng sản phẩm và cùng khách hàng không? Trong phần lớn trường hợp, câu trả lời là **có**. Vì vậy, một giá trị dùng để tìm kiếm theo nghiệp vụ chưa chắc phù hợp làm khóa chính lâu dài.

JPA hỗ trợ cả **khóa nghiệp vụ (business key/natural key)** và **khóa thay thế (surrogate key)**. Điều quan trọng là chọn đúng theo tính chất của miền nghiệp vụ, đồng thời hiểu rõ sự khác nhau giữa **danh tính của entity** và **quy tắc duy nhất của dữ liệu**.

## 1. Các khái niệm định danh cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Khóa ứng viên (*candidate key*) | Tập thuộc tính tối thiểu có thể xác định duy nhất một hàng theo quy tắc dữ liệu | Số đăng ký công ty trong một hệ thống có phạm vi rõ ràng |
| Khóa chính (*primary key, PK*) | Khóa được chọn làm định danh chính của hàng, có ràng buộc PK trong database | `customer_id` |
| Khóa nghiệp vụ (*business/natural key*) | Giá trị hoặc tập giá trị xuất phát từ khái niệm nghiệp vụ và dùng để nhận diện đối tượng | `(tenant_id, customer_code)` |
| Khóa thay thế (*surrogate key*) | Giá trị định danh do hệ thống cấp, không mang ý nghĩa nghiệp vụ trực tiếp | `id = 851203` hoặc một UUID |
| Khóa thay thế theo nghĩa *alternate key* | Khóa ứng viên duy nhất nhưng không được chọn làm PK | `UNIQUE(tenant_id, customer_code)` khi PK là `id` |
| Khóa ngoại (*foreign key, FK*) | Cột hoặc nhóm cột tham chiếu khóa được DB cho phép ở bảng khác | `order.customer_id → customers.id` |
| Khóa ghép (*composite key*) | Khóa gồm nhiều thuộc tính | `(order_id, line_number)` |

Trong bài, **surrogate key** được dịch là *khóa thay thế* để phân biệt với *khóa nghiệp vụ*. Khi dùng thuật ngữ “khóa thay thế” trong nhóm dự án, nên nói rõ nghĩa này vì một số tài liệu dịch *alternate key* cũng bằng cụm từ gần giống. Một khóa nghiệp vụ vẫn có thể là **alternate key có ràng buộc UNIQUE** dù không được chọn làm primary key.

### Danh tính khác với thuộc tính mô tả

Giả sử khách hàng đã đăng ký với email `an@example.com`, sau đó đổi thành `an.new@example.com`. Hệ thống cần bảo toàn đơn hàng, địa chỉ giao hàng và lịch sử thanh toán của **cùng một người dùng**. Nếu email là PK, một thay đổi hồ sơ trở thành thay đổi định danh. Nếu PK là `customer_id` bất biến, email chỉ là thuộc tính nghiệp vụ có thể cập nhật.

**Khóa chính nhằm trả lời “đây là bản ghi nào?”; khóa nghiệp vụ thường trả lời “nghiệp vụ nhận diện hoặc tra cứu đối tượng này bằng tiêu chí gì?”.** Hai câu hỏi có thể có cùng đáp án trong một miền dữ liệu ổn định, nhưng không nên mặc định điều đó.

## 2. JPA sử dụng khóa chính để làm gì?

Theo mô hình Jakarta Persistence, mỗi entity phải có định danh được mô tả qua `@Id`, `@EmbeddedId` hoặc các cách khai báo khóa phù hợp. Giá trị định danh là cơ sở để provider nhận biết một entity trong **persistence context**.

~~~java
Customer a = em.find(Customer.class, 42L);
Customer b = em.find(Customer.class, 42L);

System.out.println(a == b);
// Trong cùng persistence context, cùng kiểu entity và cùng khóa
// thường được đại diện bởi cùng instance managed.
~~~

Khi ánh xạ khóa chính bằng `@Id`, JPA cung cấp một danh tính nhất quán cho thao tác `find`, `merge`, `remove`, liên kết entity và theo dõi thay đổi. Nhưng cần tách biệt:

- **JPA identity:** loại entity + giá trị khóa chính trong persistence context.
- **Database primary key:** một ràng buộc vật lý trên bảng để xác định duy nhất hàng.
- **Java object identity:** toán tử `==` so sánh hai tham chiếu object.
- **Java object equality:** `equals()` là hợp đồng do lập trình viên thiết kế; JPA không tự đồng nhất nó với PK trong mọi ngữ cảnh.

Trong ví dụ quản lý danh tính, `Customer.class` và `42L` cùng góp phần tạo nên danh tính JPA. Không nên suy ra rằng hai object detached cùng ID luôn có cùng tham chiếu Java hoặc mặc nhiên có `equals() == true`.

## 3. Khóa nghiệp vụ: giá trị có ý nghĩa trong domain

Khóa nghiệp vụ xuất phát từ quy tắc xác định đối tượng của tổ chức. Ví dụ:

- Mã ISO của một quốc gia trong tập danh mục áp dụng một tiêu chuẩn cụ thể.
- Mã sản phẩm nội bộ nếu tổ chức cam kết mỗi mã tồn tại duy nhất và không đổi trong suốt vòng đời.
- Số tài khoản trong phạm vi một ngân hàng, kèm mã ngân hàng nếu tính duy nhất chỉ có hiệu lực trong từng ngân hàng.
- Mã sinh viên trong phạm vi một trường, kèm định danh trường khi quản lý nhiều đơn vị.
- `(tenant_id, invoice_number)` khi số hóa đơn chỉ duy nhất theo từng khách thuê hệ thống.

Một khóa nghiệp vụ hợp lệ phải được xét trong **phạm vi của nó**. Ví dụ `invoice_number = "INV-001"` không nhất thiết là duy nhất toàn hệ thống. Hai công ty khác nhau có thể cùng sử dụng số này. Nếu hệ thống phục vụ nhiều công ty, khóa ứng viên có thể là `(company_id, invoice_number)`.

### Đặc điểm của khóa nghiệp vụ tốt

1. **Duy nhất:** không có hai đối tượng hợp lệ dùng cùng giá trị trong phạm vi đã định.
2. **Ổn định:** giá trị không bị đổi vì chỉnh sửa tên, định dạng hoặc quy trình vận hành thông thường.
3. **Có sẵn ở thời điểm tạo:** không cần chờ nhiều bước xử lý mới xác định được khóa.
4. **Không được tái sử dụng sai nghĩa:** một mã cũ không bị cấp lại cho đối tượng hoàn toàn khác nếu lịch sử còn tham chiếu tới mã đó.
5. **Có quy tắc so sánh rõ:** chữ hoa/thường, khoảng trắng, Unicode, dấu tiếng Việt, mã quốc gia và định dạng được chuẩn hóa nhất quán.
6. **Có giới hạn phạm vi xác định:** biết rõ tính duy nhất áp dụng toàn hệ thống, theo tenant, theo năm hay theo một hệ thống bên ngoài.

Nếu thiếu một trong những tính chất này, việc chọn khóa nghiệp vụ làm PK có thể tạo ra chi phí cao khi yêu cầu thay đổi.

### Những giá trị tưởng ổn định nhưng thường thay đổi

| Giá trị | Vì sao có rủi ro khi làm PK? |
| --- | --- |
| Email | Người dùng đổi email; email có thể dùng chung hoặc thay đổi chính sách xác thực |
| Số điện thoại | Đổi số, chuyển chủ, tái cấp số và vấn đề mã quốc gia |
| Tên đăng nhập | Có thể cho phép đổi tên; quy tắc không phân biệt hoa/thường có thể thay đổi |
| Mã SKU | Nhà cung cấp thay chuẩn mã, gộp SKU hoặc đổi danh mục |
| Biển số xe | Có thể đổi, phụ thuộc khu vực và lịch sử đăng ký |
| Mã nhân viên | Có thể thay khi sát nhập công ty, chuyển đơn vị hoặc nhập dữ liệu cũ |
| Số hóa đơn | Có thể chỉ duy nhất theo đơn vị phát hành, năm hoặc chuỗi |
| Mã do hệ thống bên ngoài cấp | Đối tác có thể đổi định dạng hoặc hủy/tái cấp mã |

Không phải mọi giá trị trên đều **không thể** làm PK. Vấn đề là phải xác minh tính chất của chúng theo quy tắc nghiệp vụ có thể duy trì lâu dài, chứ không chỉ dựa trên dữ liệu mẫu hiện tại.

## 4. Khóa thay thế: danh tính do hệ thống cấp

**Surrogate key** là giá trị được cấp cho mục đích định danh bản ghi, thường không mang thông tin nghiệp vụ:

~~~text
customers
-----------------------------------------------------------
id       tenant_id    customer_code   email
-----------------------------------------------------------
1001     7            CUS-001         an@example.com
1002     7            CUS-002         binh@example.com
1003     9            CUS-001         chi@example.com
~~~

Ở ví dụ này:

- `id` là surrogate PK, duy nhất cho mọi hàng của bảng.
- `(tenant_id, customer_code)` là khóa nghiệp vụ duy nhất **trong từng tenant**.
- Mã `CUS-001` có thể lặp lại ở tenant 7 và tenant 9.
- Các bảng liên quan có thể tham chiếu `customers.id` bằng FK một cột.

Surrogate key thường được cấp bằng sequence, identity column, UUID hoặc cơ chế cấp định danh khác. Điểm mấu chốt không phải dùng số hay chuỗi, mà là **giá trị không đổi theo nội dung nghiệp vụ của đối tượng**.

### Ưu điểm của surrogate PK

- Định danh ổn định khi tên, email, mã khách hàng hoặc quy tắc kinh doanh thay đổi.
- Dễ tạo khóa ngoại nhỏ, đặc biệt khi surrogate là số nguyên.
- Hạn chế lan truyền dữ liệu có ý nghĩa nghiệp vụ hoặc nhạy cảm sang các bảng con.
- Dễ biểu diễn một entity có nhiều mã từ các hệ thống tích hợp khác nhau.
- Hạn chế phải cập nhật hàng loạt khóa ngoại khi tổ chức đổi mã nghiệp vụ.
- Có thể cấp định danh ngay cả khi chưa nhận được mã từ đối tác.

### Giới hạn của surrogate PK

- **Không tự bảo đảm dữ liệu nghiệp vụ duy nhất.** Nếu quên unique constraint, hai hàng vẫn có thể cùng mã khách hàng hoặc mã ngoài.
- Thêm một cột và thường thêm index so với khóa nghiệp vụ được chọn làm PK trực tiếp.
- Cần truy vấn thêm qua khóa nghiệp vụ khi người dùng chỉ biết mã ngoài.
- Chiến lược sinh ID có thể ảnh hưởng hiệu năng insert và cách ứng dụng phân tán cấp mã.
- Surrogate ID là định danh kỹ thuật, không tự đồng nghĩa với quyền được xem/sửa bản ghi.

Nhiều hệ thống phù hợp với mô hình kết hợp: **surrogate key làm PK, business key được ràng buộc UNIQUE**.

## 5. Bảng so sánh hai chiến lược

| Tiêu chí | Khóa nghiệp vụ làm PK | Khóa thay thế làm PK |
| --- | --- | --- |
| Ý nghĩa | Định danh phản ánh nghiệp vụ | Định danh chỉ có ý nghĩa kỹ thuật |
| Nguồn giá trị | Quy tắc nghiệp vụ/đối tác/người dùng | Hệ thống tạo hoặc phân phối |
| Nguy cơ thay đổi | Phụ thuộc chính sách nghiệp vụ | Thấp nếu thiết kế ID bất biến |
| Khóa ngoại | Có thể dài hoặc nhiều cột | Thường một cột đơn giản |
| Người dùng nhận biết | Có thể đọc và trao đổi trực tiếp | Thường không có ý nghĩa với người dùng |
| Tích hợp bên ngoài | Có thể phải xử lý đổi mã của nguồn | Có thể lưu nhiều mã ngoài như thuộc tính |
| Chống trùng nghiệp vụ | PK chỉ chặn trùng theo giá trị PK đã chọn | Cần thêm UNIQUE cho business key |
| Độ đơn giản mô hình | Có lợi nếu business key thật sự đơn giản, bất biến | Có lợi khi domain biến đổi hoặc nhiều nguồn dữ liệu |
| Kế thừa quy tắc định danh qua hệ thống | Dễ phụ thuộc mạnh vào một mã nghiệp vụ | Có thể tách ID nội bộ khỏi mã tích hợp |

Lựa chọn không có đáp án đúng cho mọi bảng. Ví dụ bảng danh mục quốc gia theo chuẩn ISO có mã hai ký tự ổn định trong phạm vi nghiệp vụ có thể dùng mã làm PK. Nhưng bảng tài khoản khách hàng thường cần định danh bền vững độc lập với email và số điện thoại.

## 6. Ví dụ JPA: dùng khóa nghiệp vụ trực tiếp làm `@Id`

Giả sử ứng dụng có bảng mã đơn vị tiền tệ trong tập dữ liệu nhỏ, quản lý theo mã ba ký tự và yêu cầu nghiệp vụ không cho sửa mã sau khi tạo. Mã là một lựa chọn có cơ sở làm natural PK.

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "currencies")
public class CurrencyInfo {

    @Id
    @Column(name = "code", length = 3, nullable = false, updatable = false)
    private String code;

    @Column(name = "display_name", nullable = false, length = 100)
    private String displayName;

    protected CurrencyInfo() {
        // JPA yêu cầu constructor không tham số phù hợp.
    }

    public CurrencyInfo(String code, String displayName) {
        this.code = code;
        this.displayName = displayName;
    }

    public String getCode() {
        return code;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Vì `@Id` nằm trên field nên mapping dùng **field access**. Các hàng được định danh bằng mã như `VND` hoặc `USD`:

~~~java
CurrencyInfo vnd = em.find(CurrencyInfo.class, "VND");
~~~

DDL minh họa:

~~~sql
CREATE TABLE currencies (
    code VARCHAR(3) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL
);
~~~

**Điểm quan trọng:** trường `code` được ứng dụng gán trước khi `persist`. Không có lý do dùng `@GeneratedValue` cho một mã do nghiệp vụ quyết định. `updatable = false` là metadata ánh xạ yêu cầu provider không đưa cột này vào UPDATE thường xuyên; nó **không** thay thế cơ chế bảo vệ bất biến bằng ứng dụng và database.

Nếu mai sau mã chuẩn được đổi hoặc tổ chức cho phép nhập một mã thay thế, cần xem xét chính sách chuyển đổi và FK. Ngay cả mã danh mục cũng không mặc nhiên bất biến mãi mãi.

## 7. Ví dụ JPA: surrogate PK và business key duy nhất

Trong ứng dụng quản lý khách hàng nhiều tenant, một khách hàng có:

- `id`: định danh nội bộ, không đổi.
- `tenantId`: tenant sở hữu.
- `customerCode`: mã khách hàng duy nhất trong tenant.
- `email`: thông tin liên hệ có thể thay đổi.

Đây là thiết kế thường dễ bảo trì khi mã khách hàng có thể được thay đổi theo quy trình nghiệp vụ.

### 7.1. Định nghĩa entity

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customer_tenant_code",
        columnNames = {"tenant_id", "customer_code"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private Long tenantId;

    @Column(name = "customer_code", nullable = false, length = 40)
    private String customerCode;

    @Column(name = "email", length = 320)
    private String email;

    protected Customer() {
    }

    public Customer(Long tenantId, String customerCode, String email) {
        this.tenantId = tenantId;
        this.customerCode = customerCode;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public void changeCustomerCode(String newCode) {
        this.customerCode = newCode;
    }

    public String getEmail() {
        return email;
    }

    public void changeEmail(String newEmail) {
        this.email = newEmail;
    }
}
~~~

Trong entity này, `@GeneratedValue(strategy = GenerationType.IDENTITY)` yêu cầu sinh surrogate ID theo cơ chế identity do database/provider hỗ trợ. Annotation `@UniqueConstraint` biểu diễn metadata rằng tổ hợp `(tenant_id, customer_code)` phải duy nhất khi sinh schema. **Database đang sử dụng phải thực sự có unique constraint tương ứng**; annotation không tự đảm bảo schema đã triển khai được cập nhật.

### 7.2. DDL tương ứng trong PostgreSQL

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_code VARCHAR(40) NOT NULL,
    email VARCHAR(320),
    CONSTRAINT uq_customer_tenant_code
        UNIQUE (tenant_id, customer_code)
);
~~~

Để tìm khách hàng theo mã nghiệp vụ:

~~~java
Customer customer = em.createQuery(
        "SELECT c FROM Customer c "
      + "WHERE c.tenantId = :tenantId "
      + "AND c.customerCode = :customerCode",
        Customer.class)
    .setParameter("tenantId", 7L)
    .setParameter("customerCode", "CUS-001")
    .getSingleResult();
~~~

`getSingleResult()` ném exception nếu không tìm thấy hoặc nếu kết quả không đúng kỳ vọng. Ứng dụng thực tế cần xử lý trường hợp không tồn tại theo giao thức nghiệp vụ; uniqueness ở database giúp loại bỏ nhiều kết quả cho tổ hợp khóa đã xác định.

### 7.3. Tại sao vẫn phải giữ unique constraint?

Nếu chỉ dùng `id` làm PK, database vẫn có thể nhận hai hàng:

~~~text
id=1001, tenant_id=7, customer_code=CUS-001
id=1004, tenant_id=7, customer_code=CUS-001
~~~

Hai hàng có hai surrogate ID khác nhau, nên primary key **không phát hiện trùng mã khách hàng**. Unique constraint trên `(tenant_id, customer_code)` mới thể hiện quy tắc nghiệp vụ. Đây là khác biệt quan trọng nhất khi dùng surrogate PK: **khóa kỹ thuật không thay thế kiểm soát trùng nghiệp vụ**.

## 8. Khóa ngoại và chi phí của việc đổi mã nghiệp vụ

Giả sử khách hàng có nhiều đơn hàng. Khi dùng surrogate PK, quan hệ JPA có thể viết:

~~~java
package com.example.persistence;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "sales_orders")
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected SalesOrder() {
    }

    public SalesOrder(Customer customer) {
        this.customer = customer;
    }
}
~~~

DDL minh họa:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_sales_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Nếu khách hàng đổi mã từ `CUS-001` thành `CUS-NEW-001`, chỉ cột `customers.customer_code` cần đổi; `sales_orders.customer_id` vẫn tham chiếu cùng khách hàng.

Nếu PK là chuỗi mã nghiệp vụ và các bảng con tham chiếu trực tiếp mã đó, việc đổi mã có thể đòi hỏi:

- Cập nhật khóa ngoại trên nhiều bảng hoặc cấu hình `ON UPDATE CASCADE` phù hợp.
- Xem xét tác động đến index, lịch sử, hệ thống đồng bộ và API.
- Xử lý transaction khi cập nhật nhiều quan hệ.
- Tránh ảnh hưởng bởi dữ liệu ngoài hệ thống còn lưu mã cũ.

Khóa thay thế giảm sự phụ thuộc này, nhưng **không tự giải quyết yêu cầu cách ly tenant**. Ở hệ thống đa tenant, truy vấn phải lọc tenant đúng cách; nếu muốn database chặn tham chiếu chéo tenant bằng cấu trúc FK, có thể cần đưa `tenant_id` vào khóa duy nhất và khóa ngoại ghép hoặc áp dụng mô hình schema/row-level security phù hợp.

## 9. Các chiến lược sinh surrogate key trong JPA

JPA định nghĩa `@GeneratedValue` để yêu cầu provider sinh giá trị định danh theo chiến lược phù hợp. Điều này **chỉ áp dụng cho việc cấp ID**, không tự làm cho khóa đó trở thành business key.

| Chiến lược | Cách hiểu | Điểm cân nhắc |
| --- | --- | --- |
| `GenerationType.IDENTITY` | Database sinh ID khi INSERT vào cột identity | Đơn giản; thời điểm có ID và batching chịu ảnh hưởng provider/DBMS |
| `GenerationType.SEQUENCE` | Lấy ID từ sequence | Có thể cấp trước INSERT và tối ưu phân bổ theo block; cần sequence phù hợp |
| `GenerationType.TABLE` | Dùng bảng đặc biệt để cấp ID | Di động ở một số môi trường nhưng có nguy cơ contention |
| `GenerationType.AUTO` | Để provider chọn chiến lược | Hành vi phụ thuộc provider và dialect |
| `GenerationType.UUID` | Yêu cầu sinh UUID theo hỗ trợ của chuẩn hiện đại | Cần phiên bản Jakarta Persistence/provider hỗ trợ; cân nhắc kiểu cột và index |

### 9.1. SEQUENCE

~~~java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_seq_gen")
@SequenceGenerator(
    name = "customer_seq_gen",
    sequenceName = "customer_id_seq",
    allocationSize = 50)
private Long id;
~~~

Trên DBMS hỗ trợ sequence, có thể cấp ID trước khi INSERT. `allocationSize` cho phép provider lấy một nhóm ID để giảm số lần gọi sequence theo cơ chế triển khai; cần đồng bộ cấu hình với sequence vật lý và chiến lược tối ưu của provider. **ID bị nhảy số là điều bình thường** do rollback, cache, phân bổ theo nhóm hoặc transaction bị hủy. Không dùng surrogate ID làm số thứ tự nghiệp vụ yêu cầu liên tục.

### 9.2. UUID

Trong các phiên bản Jakarta Persistence mới hỗ trợ `GenerationType.UUID`, có thể khai báo:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.util.UUID;

@Entity
public class Document {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected Document() {
    }
}
~~~

`GenerationType.UUID` được bổ sung trong Jakarta Persistence 3.1; dự án dùng phiên bản cũ có thể cần cơ chế riêng của provider. Không tự giả định UUID được sinh theo một phiên bản thuật toán cụ thể nếu điều đó không được cam kết bởi stack.

UUID thuận tiện khi cần sinh ID phân tán trước khi chạm database hoặc phối hợp nhiều nguồn dữ liệu. Đổi lại, kích thước khóa/index và tính cục bộ của khóa có thể khác số tăng dần. Nếu cần ID được sắp xếp theo thời gian, phải chọn và kiểm tra một cơ chế tạo ID có tính chất đó; **không dùng giá trị ID thay cho timestamp nghiệp vụ**.

### 9.3. IDENTITY, SEQUENCE và batch insert

Với `IDENTITY`, provider thường cần tương tác với database để nhận ID sau INSERT, có thể hạn chế tối ưu batching trong một số provider. `SEQUENCE` có thể thuận lợi hơn khi cấp trước nhiều ID, nhưng còn tùy hệ quản trị và cấu hình.

Quyết định lựa chọn surrogate key và quyết định **cấp surrogate key bằng thuật toán nào** là hai bước khác nhau. Đầu tiên xác định mô hình định danh; sau đó chọn cơ chế cấp ID phù hợp khả năng DBMS và yêu cầu ghi dữ liệu.

## 10. Khi khóa nghiệp vụ gồm nhiều thuộc tính

Một khóa nghiệp vụ không nhất thiết là một chuỗi duy nhất. Ví dụ một mặt hàng được nhận diện bởi `(tenant_id, catalog_code)`, vì mã catalog chỉ duy nhất trong tenant.

Nếu thực sự muốn dùng tổ hợp này làm PK, JPA hỗ trợ khóa ghép qua `@EmbeddedId` hoặc `@IdClass`.

### 10.1. Khai báo `@EmbeddedId`

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class CatalogEntryId implements Serializable {

    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "catalog_code", length = 40)
    private String catalogCode;

    protected CatalogEntryId() {
    }

    public CatalogEntryId(Long tenantId, String catalogCode) {
        this.tenantId = tenantId;
        this.catalogCode = catalogCode;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getCatalogCode() {
        return catalogCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CatalogEntryId)) {
            return false;
        }
        CatalogEntryId that = (CatalogEntryId) other;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(catalogCode, that.catalogCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, catalogCode);
    }
}
~~~

Entity dùng khóa ghép:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_entries")
public class CatalogEntry {

    @EmbeddedId
    private CatalogEntryId id;

    @Column(name = "unit_price", nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    protected CatalogEntry() {
    }

    public CatalogEntry(CatalogEntryId id, BigDecimal unitPrice) {
        this.id = id;
        this.unitPrice = unitPrice;
    }

    public CatalogEntryId getId() {
        return id;
    }
}
~~~

Tìm theo khóa ghép:

~~~java
CatalogEntryId key = new CatalogEntryId(7L, "CAT-001");
CatalogEntry entry = em.find(CatalogEntry.class, key);
~~~

DDL tương ứng:

~~~sql
CREATE TABLE catalog_entries (
    tenant_id BIGINT NOT NULL,
    catalog_code VARCHAR(40) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, catalog_code)
);
~~~

**Lưu ý:** lớp khóa ghép cần thiết kế ngữ nghĩa so sánh và `hashCode` dựa trên các thành phần định danh, có constructor không tham số phù hợp và tuân thủ các yêu cầu khác của JPA. Giá trị khóa ghép nên được coi là bất biến sau khi entity đã được lưu. Với key mutable, thay đổi thành phần có thể phá vỡ cơ chế nhận diện entity trong persistence context và các FK tham chiếu.

### 10.2. Đánh đổi của khóa ghép

Khóa ghép có thể rất tự nhiên về nghiệp vụ và chặn trùng thông qua PK. Tuy nhiên:

- Mọi bảng con tham chiếu khóa đó có thể cần nhiều cột FK.
- API phải truyền đủ mọi thành phần khóa.
- Nếu một thành phần thay đổi, việc cập nhật PK và FK có thể phức tạp.
- Khóa rộng có thể làm index và join nặng hơn.
- Entity mapping, query và serialization thường nhiều mã hơn.

Vì vậy, nếu `catalog_code` có khả năng đổi, một phương án khác là tạo `catalog_entry_id` làm surrogate PK, giữ `UNIQUE(tenant_id, catalog_code)` và đặt FK của bảng con theo ID.

## 11. Trường hợp khóa ghép vẫn là lựa chọn tốt

Không nên mặc định mọi khóa ghép đều phải chuyển sang surrogate. Khóa ghép phù hợp khi **danh tính của hàng thực sự phụ thuộc vào tổ hợp định danh ổn định**.

Ví dụ bảng quan hệ có thuộc tính:

~~~sql
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    granted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (role_id) REFERENCES roles(id)
);
~~~

Nếu quy tắc là “mỗi người dùng chỉ có một quan hệ gán với mỗi vai trò”, tổ hợp `(user_id, role_id)` là PK tự nhiên của hàng liên kết. Thêm `user_role_id` là một phương án khác, nhưng khi đó **vẫn cần UNIQUE(user_id, role_id)** để chống gán trùng.

Một ví dụ khác là dòng đơn hàng với `(order_id, line_number)`. Số dòng ổn định trong phạm vi đơn hàng có thể là PK, nhưng nếu người dùng được phép đánh lại thứ tự dòng, cần phân biệt **số thứ tự hiển thị** với **định danh dòng**. Trong trường hợp đó, surrogate ID cho từng dòng có thể ít gây thay đổi dây chuyền hơn.

## 12. Cách dùng `@MapsId` khi khóa phụ thuộc entity cha

JPA có `@MapsId` để ánh xạ một phần hoặc toàn bộ khóa của entity từ quan hệ với entity khác. Ví dụ dòng đơn hàng dùng `order_id` và `line_number` làm khóa ghép:

~~~java
@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId)) return false;
        OrderLineId that = (OrderLineId) other;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

~~~java
@Entity
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    protected OrderLine() {
    }
}
~~~

Các đoạn minh họa giả sử đã import annotation và các lớp `Serializable`, `Objects`, `FetchType`, `SalesOrder` tương ứng. `SalesOrder` là entity có định danh Long trong ví dụ trước. `@MapsId("orderId")` khai báo rằng thành phần `orderId` của khóa ghép gắn với định danh của quan hệ `order`; provider phối hợp giá trị FK và ID.

Đây là một khả năng JPA hữu ích cho mô hình khóa phụ thuộc cha, nhưng nó **không bắt buộc** chỉ vì bảng có FK. Với surrogate PK một cột, thông thường chỉ cần `@ManyToOne` và `@JoinColumn` như ở mục 8.

## 13. Tính duy nhất của business key phải do database thực thi

Giả sử hai request cùng tạo khách hàng có mã `CUS-001`:

~~~text
Request A                         Request B
    |                                 |
SELECT mã CUS-001 chưa tồn tại    SELECT mã CUS-001 chưa tồn tại
    |                                 |
INSERT customer(id=1001, ...)     INSERT customer(id=1002, ...)
    |                                 |
    +--------- CẠNH TRANH ------------+
                    |
        UNIQUE(tenant_id, customer_code)
           tại database quyết định
~~~

Nếu ứng dụng chỉ kiểm tra trước bằng SELECT mà database không có unique constraint, cả hai request có thể tạo bản ghi trùng business key. **Kiểm tra trước không thay thế constraint** vì khoảng thời gian giữa kiểm tra và ghi vẫn có thể có request khác.

Khi database có unique constraint, một thao tác xung đột có thể bị chặn, chờ rồi thất bại hoặc phát lỗi tại flush/commit tùy DBMS, isolation và trạng thái transaction. Ứng dụng cần rollback phù hợp và chuyển lỗi thành thông báo nghiệp vụ như “Mã khách hàng đã tồn tại”.

### JPA metadata và constraint vật lý là hai chuyện khác nhau

~~~java
@Column(name = "customer_code", unique = true)
private String customerCode;
~~~

`unique = true` là metadata có thể được dùng khi JPA sinh schema; nó không chứng minh database đang chạy thật sự có constraint. Với uniqueness theo nhiều cột, `@Table(uniqueConstraints = ...)` diễn đạt rõ metadata, nhưng cũng cần migration tương ứng.

Ví dụ, hệ thống có nhiều tenant cần:

~~~sql
CONSTRAINT uq_customer_tenant_code
    UNIQUE (tenant_id, customer_code)
~~~

Đặt riêng `UNIQUE(customer_code)` sẽ sai nếu các tenant được phép trùng mã. Ngược lại, đặt UNIQUE theo tenant khi nghiệp vụ yêu cầu mã duy nhất toàn cầu cũng là sai phạm vi.

## 14. Những chi tiết ngầm ảnh hưởng đến “duy nhất”

### 14.1. Chữ hoa/thường và chuẩn hóa mã

Database có thể dùng collation phân biệt hoặc không phân biệt chữ hoa/thường. Nếu nghiệp vụ xem `CUS-001` và `cus-001` là cùng mã, phải lựa chọn một cơ chế thống nhất:

- Chuẩn hóa thành mã canonical trước khi lưu, ví dụ theo chính sách uppercase rõ ràng.
- Hoặc sử dụng collation, expression index hay generated column phù hợp DBMS.
- Đảm bảo **unique constraint** thực thi cùng ngữ nghĩa so sánh mà ứng dụng sử dụng.

Ví dụ một quy tắc cho mã sản phẩm ASCII:

~~~java
import java.util.Locale;

public static String normalizeCode(String input) {
    if (input == null) {
        throw new IllegalArgumentException("Mã không được null");
    }
    String result = input.trim().toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException("Mã không được rỗng");
    }
    return result;
}
~~~

Đây chỉ là **quy tắc ví dụ dành cho một loại mã do doanh nghiệp định nghĩa**, không áp dụng mặc định cho email, tên người hay mọi chuỗi Unicode. Khi domain có ký tự quốc tế, cần xác định thêm normalization Unicode, độ dài và collation.

### 14.2. NULL và uniqueness

Quy tắc UNIQUE cho giá trị NULL có thể khác nhau giữa DBMS và chế độ cấu hình. Với business key thực sự bắt buộc, đặt `NOT NULL` trên các thành phần khóa và thêm kiểm tra đầu vào tương ứng.

Nếu business key chưa có tại thời điểm tạo, nên cân nhắc surrogate PK và unique constraint có điều kiện phù hợp thay vì dùng một giá trị giả như `"PENDING"` cho mọi bản ghi.

### 14.3. Soft delete và tái sử dụng mã

Giả sử bản ghi có `deleted_at` và ứng dụng không xóa vật lý. Khi “xóa” khách hàng mã `CUS-001`, doanh nghiệp có thể cho phép tạo khách hàng khác cùng mã. Unique constraint toàn bảng vẫn chặn điều này.

Một số DBMS hỗ trợ **partial/filtered unique index** trên các hàng đang hoạt động, ví dụ minh họa PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_active_customer_tenant_code
ON customers (tenant_id, customer_code)
WHERE deleted_at IS NULL;
~~~

Đoạn trên chỉ áp dụng nếu schema có cột `deleted_at` và đã lựa chọn **thay thế** constraint UNIQUE toàn bảng bằng cơ chế phù hợp; nếu giữ constraint toàn bảng, index mới không làm cho việc tái sử dụng mã được phép. Đây là thiết kế phụ thuộc DBMS và quy tắc nghiệp vụ, không thể diễn đạt hoàn toàn bằng `@Column(unique=true)`.

### 14.4. Tái sử dụng khóa trong lịch sử

Ngay cả khi mã đã “ngừng sử dụng”, một bản ghi có thể còn được tham chiếu từ hóa đơn, log, báo cáo hoặc hệ thống tích hợp. Nếu gán lại cùng mã cho đối tượng khác, thao tác tra cứu theo mã và thời điểm có thể trở nên mơ hồ. Cần một chính sách rõ về **không tái sử dụng**, hoặc mô hình hóa tính hiệu lực theo khoảng thời gian, tenant và lịch sử.

## 15. Đừng dùng surrogate ID làm số thứ tự nghiệp vụ

Một khóa tự tăng như `1001, 1002, 1005` không bảo đảm liên tục vì transaction rollback, cache sequence, xung đột hoặc phân bổ ID song song. Do đó không nên sử dụng `customer_id` làm:

- Số hóa đơn phải tuân thủ quy định đánh số.
- Số phiếu thứ tự liên tục không được thiếu.
- Số lượt giao dịch trong ngày.
- Thông tin mang ý nghĩa thời gian tạo chính xác.

Nếu domain yêu cầu số chứng từ liên tục hoặc có quy tắc theo chi nhánh/năm, cần một **cơ chế cấp số nghiệp vụ riêng** có transaction và kiểm soát xung đột phù hợp. Có thể lưu số chứng từ ở cột riêng, ràng buộc uniqueness theo đúng phạm vi, và vẫn giữ surrogate PK cho định danh bản ghi.

Số surrogate ID tăng dần thường có tương quan với thứ tự cấp ID, nhưng không phải đảm bảo thứ tự commit hoặc thời điểm nghiệp vụ; không dùng `ORDER BY id` thay cho `ORDER BY created_at` nếu cần sắp theo thời gian.

## 16. Khóa nghiệp vụ trong tích hợp giữa nhiều hệ thống

Một khách hàng có thể được biết đến qua:

~~~text
internal_id     = 1001
crm_customer_id = CRM-7849
erp_account_no  = A-00510
legacy_code     = OLD-101
~~~

Nếu dùng `crm_customer_id` làm PK của ứng dụng, việc đổi CRM hoặc hợp nhất dữ liệu có thể đòi hỏi thay đổi toàn bộ FK. Một mô hình linh hoạt hơn:

~~~sql
CREATE TABLE customer_external_ids (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    source_system VARCHAR(40) NOT NULL,
    external_id VARCHAR(150) NOT NULL,
    CONSTRAINT uq_external_customer
        UNIQUE (source_system, external_id),
    CONSTRAINT fk_external_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Trong thiết kế này, `customers.id` là định danh nội bộ; bảng liên kết giữ nhiều khóa nghiệp vụ từ các hệ thống bên ngoài. Uniqueness của `(source_system, external_id)` diễn đạt rằng trong một nguồn dữ liệu, mỗi mã ngoài ánh xạ tới một khách hàng nội bộ tại một thời điểm theo quy tắc đã chọn.

Nếu cùng mã bên ngoài có thể thuộc nhiều tenant, cần thêm `tenant_id` vào phạm vi uniqueness và mô hình quan hệ tương ứng. Nếu một mã ngoài có thể được cấp lại theo thời gian, cần phiên bản hoặc khoảng hiệu lực.

Một surrogate key không giải quyết tự động bài toán **hợp nhất hai hồ sơ trùng người**. Đó là bài toán nhận diện thực thể theo nghiệp vụ, đối soát, audit và chuyển quan hệ có kiểm soát.

## 17. Khóa trong API: định danh công khai và phân quyền

Có thể dùng cùng surrogate ID trong database và URL:

~~~text
GET /customers/1001
~~~

Hoặc có một ID công khai riêng, ví dụ UUID, tách khỏi ID nội bộ. Cách thứ hai hữu ích khi:

- Không muốn công khai số thứ tự nội bộ.
- Cần tạo ID phân tán hoặc đối chiếu qua nhiều dịch vụ.
- Muốn thay đổi cách lưu dữ liệu nội bộ mà không phá hợp đồng API công khai.

Tuy nhiên, **UUID hoặc ID khó đoán không thay thế kiểm tra quyền truy cập**. Mọi API vẫn phải xác minh người gọi có quyền xem hoặc cập nhật thực thể thuộc tenant, tổ chức hoặc chủ sở hữu tương ứng.

Không nên dùng email, số giấy tờ hay thông tin nhạy cảm làm đường dẫn định danh chính chỉ vì chúng “duy nhất”. Việc xuất hiện trong URL, log, cache và thông tin giám sát có thể gây rủi ro riêng tư.

## 18. Java `equals()` và `hashCode()` khi ID được sinh sau

Với khóa nghiệp vụ thực sự bất biến và duy nhất, có thể cân nhắc equality dựa trên business key. Với surrogate ID được sinh khi persist, cần cẩn trọng:

~~~java
Customer a = new Customer(7L, "CUS-001", "a@example.com");
Customer b = new Customer(7L, "CUS-001", "b@example.com");

// Trước persist, cả a và b có thể có id == null.
~~~

Nếu viết `equals()` chỉ bằng `Objects.equals(id, other.id)`, hai entity mới có `id == null` có thể bị coi là bằng nhau mặc dù là hai object khác nhau. Nếu viết `hashCode()` dựa trên ID và ID thay đổi từ null sang số sau persist, đối tượng đã nằm trong `HashSet` có thể khó tìm lại.

Một quy ước cho **entity đơn giản không có kế thừa** là:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) {
        return true;
    }
    if (!(other instanceof Customer)) {
        return false;
    }
    Customer that = (Customer) other;
    return getId() != null && getId().equals(that.getId());
}

@Override
public int hashCode() {
    return Customer.class.hashCode();
}
~~~

Đoạn minh họa ưu tiên tránh coi hai entity mới có ID null là bằng nhau và tránh hash code thay đổi khi ID được cấp. Nó **không phải công thức áp dụng nguyên xi cho mọi entity**: proxy, kế thừa, provider enhancement và hiệu năng tập hợp lớn có thể đòi hỏi điều chỉnh. Nếu không có nhu cầu thực sự về equality giữa entity, việc giữ object identity mặc định cũng là một lựa chọn hợp lý.

Không nên dùng Lombok `@Data` hoặc tự động sinh `equals/hashCode` theo tất cả field của entity có quan hệ lazy và field mutable; điều đó có thể tải thêm dữ liệu, gây đệ quy hoặc thay đổi equality khi dữ liệu nghiệp vụ đổi.

Một nguyên tắc liên quan: **không tùy tiện thay đổi trường `@Id` trên entity đã managed/persisted**. Nếu business key được phép đổi thường xuyên, đó chính là lý do nên để nó ngoài khóa chính.

## 19. Chuyển từ business PK sang surrogate PK trong hệ thống đã có dữ liệu

Giả sử hệ thống cũ có bảng:

~~~sql
CREATE TABLE products (
    sku VARCHAR(80) PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL
);
~~~

Và các bảng `order_items`, `inventory_movements` đang tham chiếu `products.sku`. Sau này, tổ chức cho phép đổi SKU và muốn chuyển sang surrogate PK.

Một kế hoạch migration ở mức kiến trúc:

1. **Khảo sát dữ liệu và FK:** liệt kê mọi bảng, job, API và hệ thống ngoài dùng SKU để định danh.
2. **Thêm cột ID mới:** lựa chọn `BIGINT`/UUID và cơ chế cấp giá trị; điền đầy đủ ID cho dữ liệu hiện hữu.
3. **Bảo đảm tính duy nhất của ID:** thiết lập UNIQUE, NOT NULL và cơ chế sinh giá trị cho bản ghi mới.
4. **Thêm FK mới ở bảng con:** điền `product_id` bằng cách join theo SKU cũ; xác minh mọi hàng đã ánh xạ chính xác.
5. **Chuyển code ứng dụng:** JPA `@Id` chuyển sang `id`, các quan hệ chuyển sang `product_id`; nghiệp vụ tiếp tục tra cứu qua SKU.
6. **Giữ uniqueness của SKU:** nếu SKU còn phải duy nhất theo quy tắc hiện hành, bổ sung UNIQUE phù hợp.
7. **Chuyển PK và FK có kiểm soát:** thay constraint khi dữ liệu và phiên bản ứng dụng đã sẵn sàng, xử lý tương thích trong giai đoạn triển khai.
8. **Dọn đường cũ sau khi xác nhận:** ngừng dùng SKU như FK kỹ thuật ở những thành phần đã được chuyển đổi.

Không nên đơn giản đổi annotation từ `@Id String sku` sang `@Id Long id` khi schema thật và các FK vẫn còn tham chiếu SKU. Migration này là **thay đổi mô hình định danh xuyên nhiều bảng**; cần xem xét transaction, khóa bảng, kế hoạch chạy nhiều phiên bản ứng dụng và rollback theo hạ tầng thực tế.

### Vì sao không dùng `ON UPDATE CASCADE` mãi mãi?

`ON UPDATE CASCADE` có thể giúp cập nhật khóa nghiệp vụ trên các bảng con trong những DBMS hỗ trợ. Tuy nhiên, nếu mã thường xuyên thay đổi hoặc có nhiều consumer ngoài database, mỗi lần đổi vẫn là một lần đổi **danh tính được chia sẻ**. Surrogate key giúp giảm phụ thuộc, nhưng quyết định migration phải dựa trên chi phí thực tế và nhu cầu tương thích.

## 20. Tiêu chí chọn khóa khi thiết kế entity mới

Đặt các câu hỏi theo thứ tự:

1. **Đối tượng có danh tính độc lập với các thuộc tính hiển thị không?** Nếu có, surrogate PK thường hợp lý.
2. **Business key có thật sự bất biến suốt vòng đời không?** Nếu có khả năng đổi, tránh dùng làm PK.
3. **Business key được tạo ở đâu?** Nếu phụ thuộc hệ thống ngoài hoặc chỉ biết sau khi tạo, surrogate PK có lợi.
4. **Phạm vi duy nhất là gì?** Toàn cầu, theo tenant, theo tổ chức, theo năm hoặc theo thời kỳ?
5. **Khóa có bao nhiêu thành phần và dài bao nhiêu?** FK nhiều cột/chuỗi dài làm tăng độ phức tạp quan hệ và index.
6. **Có tính nhạy cảm hoặc rủi ro lộ thông tin không?** Tránh dùng thông tin cá nhân làm ID kỹ thuật ở nhiều bảng/API.
7. **Có nhu cầu tạo ID phân tán, offline hoặc nhập dữ liệu nhiều nguồn không?** Cân nhắc UUID hoặc cơ chế cấp ID phù hợp.
8. **Nếu chọn surrogate PK, business key sẽ được bảo vệ bằng constraint nào?** Không được bỏ qua câu hỏi này.
9. **Nếu chọn business PK, điều gì xảy ra khi giá trị đổi hoặc bị cấp lại?** Phải có chính sách cụ thể, không chỉ giả định “chắc không đổi”.

### Ma trận quyết định minh họa

| Tình huống | Hướng lựa chọn thường hợp lý | Ghi chú |
| --- | --- | --- |
| Tài khoản người dùng, email có thể đổi | Surrogate PK | Email có thể ràng buộc duy nhất theo chính sách |
| Khách hàng có mã riêng trong từng tenant | Surrogate PK + UNIQUE(tenant, code) | Giữ ID ổn định, vẫn chặn trùng mã |
| Danh mục mã chuẩn có tập mã ổn định và giới hạn nhỏ | Có thể dùng natural PK | Xem chính sách đổi và ngừng sử dụng mã |
| Bảng gán vai trò cho người dùng, mỗi cặp chỉ có một dòng | PK ghép (user_id, role_id) hoặc surrogate + UNIQUE | Chọn theo nhu cầu tham chiếu trực tiếp tới dòng gán |
| Đơn hàng có số chứng từ pháp lý riêng | Surrogate PK + số chứng từ UNIQUE theo phạm vi | Số chứng từ không cần trùng ID nội bộ |
| Entity nhập từ nhiều hệ thống có ID ngoài khác nhau | Surrogate PK + bảng external IDs | Tránh phụ thuộc vào một nhà cung cấp |
| Dòng đơn hàng có số dòng có thể sắp xếp lại | Surrogate PK cho dòng | Số thứ tự hiển thị là thuộc tính mutable |
| Tài nguyên tạo offline trước khi đồng bộ | ID phân tán như UUID nếu stack hỗ trợ | Tính duy nhất và cấu trúc cột phải được thiết kế đồng bộ |

## 21. Ví dụ tổng hợp: đặt hàng theo business key, lưu quan hệ theo surrogate key

Giả sử API nhận một lệnh đặt hàng:

~~~json
{
  "tenantId": 7,
  "customerCode": "CUS-001",
  "clientOrderRef": "WEB-2027-0001"
}
~~~

`customerCode` là mã do người dùng biết, có tính duy nhất trong tenant; `clientOrderRef` là mã tham chiếu để tránh xử lý trùng một yêu cầu tạo đơn theo quy tắc ứng dụng.

Ứng dụng có thể xử lý theo luồng:

~~~text
API nhận (tenantId, customerCode, clientOrderRef)
                |
                v
Tra Customer theo UNIQUE(tenant_id, customer_code)
                |
                v
Kiểm tra quyền truy cập và nghiệp vụ của tenant
                |
                v
Tạo SalesOrder với FK customer_id = Customer.id
                |
                v
Lưu clientOrderRef vào cột nghiệp vụ
và ràng buộc uniqueness/idempotency theo phạm vi
                |
                v
Database commit transaction
                |
                v
Trả orderId hoặc public ID + trạng thái
~~~

Trong trường hợp này:

- Business key giúp API tìm đúng khách hàng theo ngữ cảnh.
- Surrogate key giữ quan hệ giữa đơn hàng và khách hàng ổn định.
- Unique constraint bảo vệ quy tắc mã khách hàng và mã yêu cầu ở mức database.
- Transaction bảo đảm các thao tác ghi được thực hiện nhất quán.
- Quyền truy cập tenant và idempotency là trách nhiệm của ứng dụng cùng ràng buộc dữ liệu phù hợp.

Không nên coi `clientOrderRef` như surrogate PK chỉ vì nó chứa một chuỗi có vẻ duy nhất. Mã tham chiếu client có phạm vi, chính sách tái thử và vòng đời khác với định danh nội bộ của đơn hàng.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng email làm `@Id` trong tài khoản | Đổi email thành đổi khóa chính và FK | Dùng surrogate ID, thiết lập uniqueness email theo nghiệp vụ |
| Dùng surrogate ID nhưng quên UNIQUE mã nghiệp vụ | Sinh nhiều bản ghi trùng đối tượng | Bổ sung unique constraint đúng phạm vi |
| Chỉ SELECT kiểm tra trùng trước khi INSERT | Race condition ở request đồng thời | Dùng unique constraint của DB và xử lý xung đột |
| Dùng business key gồm nhiều cột làm PK khi các thành phần mutable | Khó cập nhật FK và equality | Cân nhắc surrogate PK, để business key ở alternate unique |
| Lấy số auto-increment làm số hóa đơn liên tục | ID có gap và không bảo đảm thứ tự commit | Cơ chế cấp số chứng từ riêng |
| Đặt UNIQUE toàn cầu cho mã chỉ duy nhất theo tenant | Chặn dữ liệu hợp lệ của tenant khác | UNIQUE theo `(tenant_id, code)` |
| Coi `@Column(unique=true)` là database constraint hiện hữu | Dữ liệu có thể trùng nếu schema thiếu constraint | Migration và xác nhận schema thực tế |
| Tự tạo surrogate ID bằng `MAX(id)+1` | Tranh chấp đồng thời và cấp ID trùng | Dùng sequence/identity/UUID hoặc dịch vụ cấp ID đúng thiết kế |
| Dùng UUID như cơ chế phân quyền | ID lộ vẫn có thể bị truy cập | Kiểm tra authorization theo bản ghi và tenant |
| Đổi `@Id` trên entity managed | Phá giả định danh tính của persistence context | Giữ ID bất biến; cập nhật business key ở cột khác |
| Dùng `equals/hashCode` dựa trên ID null | Hai entity mới bị xem là bằng nhau | Thiết kế equality phù hợp trạng thái entity và provider |
| Chuẩn hóa mã trong Java khác collation của database | Trùng dữ liệu hoặc chặn dữ liệu sai ý định | Thống nhất canonicalization và uniqueness thực tế |

## 23. Bài tập vận dụng

### Bài 1 — Khách hàng có thể đổi email

Thiết kế bảng khách hàng, trong đó tài khoản được định danh ổn định, email có thể thay đổi nhưng không được trùng theo chính sách sản phẩm.

**Gợi ý:** surrogate `customer_id` làm PK, email là thuộc tính. Chọn rõ cách chuẩn hóa và UNIQUE email theo phạm vi áp dụng. Xử lý lỗi unique constraint thay vì chỉ dựa vào thao tác SELECT kiểm tra trước.

### Bài 2 — Số hóa đơn trùng giữa hai chi nhánh

Chi nhánh A và B đều có số hóa đơn `2027-001`. Tính duy nhất phải xét như thế nào?

**Gợi ý:** nếu quy tắc cho phép trùng số giữa chi nhánh, khóa nghiệp vụ là tổ hợp `(branch_id, invoice_number)`, hoặc thêm năm/loại chứng từ nếu yêu cầu. Có thể dùng surrogate `invoice_id` làm PK và unique constraint trên tổ hợp nghiệp vụ.

### Bài 3 — Mã sản phẩm được đổi

Tồn kho, đơn hàng và ảnh sản phẩm hiện tham chiếu `product.sku`. Bộ phận kinh doanh yêu cầu cho phép đổi SKU.

**Gợi ý:** đánh giá chuyển sang surrogate `product_id` ổn định; xác định migration FK, lưu lịch sử SKU nếu cần và ràng buộc uniqueness cho SKU hiện hành.

### Bài 4 — Bảng liên kết người dùng và vai trò

Mỗi người dùng chỉ có thể gắn một lần vào một vai trò. Có nhất thiết phải thêm cột `user_role_id` không?

**Gợi ý:** không nhất thiết. `PRIMARY KEY(user_id, role_id)` là phương án hợp lệ. Nếu dùng surrogate PK để có tham chiếu riêng tới bản ghi gán, vẫn cần UNIQUE hai FK.

### Bài 5 — Tạo ID từ nhiều node

Một dịch vụ nhận bản ghi offline từ nhiều thiết bị, chưa kết nối DB trung tâm khi tạo. Có thể dựa hoàn toàn vào auto-increment tại database không?

**Gợi ý:** nếu cần định danh trước khi đồng bộ, cân nhắc UUID hoặc cơ chế ID phân tán. Đồng thời thiết kế chống trùng business key và idempotency khi nhập bản ghi từ nhiều nguồn.

### Bài 6 — Mã người dùng có thể tái sử dụng sau xóa mềm

Yêu cầu mới cho phép cấp lại username sau khi tài khoản cũ ngừng hoạt động. Một `UNIQUE(username)` toàn bảng có còn phù hợp?

**Gợi ý:** phải xác định chính sách lịch sử và phạm vi duy nhất cho tài khoản đang hoạt động. Có thể cần partial unique index, bảng lịch sử hoặc mô hình version; lựa chọn phụ thuộc DBMS và rủi ro tái sử dụng định danh.

## Kết luận

**Khóa nghiệp vụ biểu đạt cách domain nhận diện một đối tượng; khóa thay thế cung cấp định danh kỹ thuật ổn định cho bản ghi.** Nếu business key thực sự ngắn, bất biến, có sẵn và duy nhất trong phạm vi xác định, dùng nó làm primary key có thể hợp lý. Nếu mã nghiệp vụ có thể đổi, phụ thuộc đối tác, chứa thông tin nhạy cảm hoặc gồm nhiều thành phần, surrogate key thường giúp đơn giản hóa quan hệ và bảo trì hệ thống.

Trong JPA, quyết định này được biểu diễn qua `@Id`, `@EmbeddedId`, `@IdClass` và `@GeneratedValue`. Dù chọn chiến lược nào, hãy duy trì ranh giới rõ giữa **danh tính entity**, **uniqueness của dữ liệu nghiệp vụ** và **cơ chế cấp ID**. Đặc biệt, surrogate PK không miễn trừ trách nhiệm thiết kế UNIQUE constraint đúng phạm vi tại database; còn natural PK đòi hỏi cam kết ổn định của giá trị qua suốt vòng đời dữ liệu.
