# Đánh giá chi phí bảo trì khi khóa nghiệp vụ có thể thay đổi

## 1. Vì sao tính thay đổi của khóa nghiệp vụ quan trọng?

Trong JPA, một entity có thể được định danh bằng **khóa ghép** (*composite primary key*), tức khóa chính gồm từ hai thuộc tính trở lên. Một cách thiết kế phổ biến là lấy các giá trị đã có trong nghiệp vụ:

- **tenant_id + sku** để nhận diện sản phẩm trong một doanh nghiệp.
- **company_id + employee_code** để nhận diện nhân viên trong công ty.
- **order_id + line_number** để nhận diện dòng thuộc đơn hàng.
- **country_code + tax_number** để nhận diện một đối tượng trong phạm vi pháp lý.

Những tổ hợp trên có thể duy nhất ở thời điểm ghi dữ liệu, nhưng không chắc giữ nguyên về sau. Doanh nghiệp có thể đổi bộ mã sản phẩm, sáp nhập chi nhánh, sửa mã nhân viên bị nhập sai, hoặc cho phép người dùng đổi thứ tự dòng đơn hàng. Nếu mã nghiệp vụ nằm trong **PRIMARY KEY**, một thao tác sửa dữ liệu thông thường trở thành **thay đổi định danh** của hàng và của entity JPA.

Điều cần đánh giá là **tổng chi phí duy trì sự nhất quán** sau thay đổi đó: khóa ngoại, cấu trúc index, persistence context, cache, API, event, lịch sử dữ liệu, migration và thời gian bảo trì vận hành.

> Khóa nghiệp vụ đang duy nhất chưa chắc là khóa chính bền vững. Khi chọn composite key, phải kiểm tra cả **tính duy nhất** và **tính bất biến của tất cả thành phần**.

## 2. Khóa nghiệp vụ và khóa kỹ thuật

**Business key** hoặc **natural key** là giá trị có ý nghĩa với người dùng hoặc hệ thống ngoài: SKU, mã nhân viên, mã chi nhánh, số hợp đồng. **Surrogate key** là định danh kỹ thuật được cấp nhằm nhận diện bản ghi, ví dụ số BIGINT từ sequence/identity hoặc UUID.

| Khía cạnh | Khóa nghiệp vụ | Khóa kỹ thuật |
|---|---|---|
| Mục đích | Giao tiếp và tìm kiếm theo quy tắc nghiệp vụ | Nhận diện bản ghi ổn định |
| Ví dụ | (tenantId, sku) | productId |
| Có thể thay đổi | Có, tùy quy trình và chính sách | Nên bất biến |
| Tính duy nhất | Theo tenant, thời gian hoặc phạm vi khác | Theo phạm vi cấp ID |
| Ý nghĩa với người dùng | Thường có | Thường không |
| Khi thay đổi | Có thể ảnh hưởng nhiều quan hệ và tích hợp | Việc đổi ID thường phải tránh |

Một bảng có thể có **PRIMARY KEY kỹ thuật** và đồng thời **UNIQUE constraint** trên business key. Cách này giữ sự duy nhất của mã nhưng không bắt những tham chiếu nội bộ phải thay ID khi mã đổi.

### 2.1. Duy nhất không đồng nghĩa bất biến

Giả sử năm 2025:

~~~text
tenant_id = 42
sku       = "USB-C-100"
name      = "Cáp USB-C 1 m"
~~~

Năm 2026, doanh nghiệp chuyển sang hệ mã mới và sản phẩm có SKU **CABLE-001**. Theo nghiệp vụ, đó vẫn là **cùng một sản phẩm**. Nếu (42, USB-C-100) là primary key, đổi SKU đồng thời đổi khóa chính. Nếu sản phẩm có productId = 1001 ổn định, ta có thể đổi sku trong khi các bảng con vẫn tham chiếu productId.

Một khóa ghép bất biến khi **mọi thành phần của nó** bất biến. tenant_id ổn định chưa đủ nếu SKU có thể đổi. Một mã có thể thay đổi mỗi năm là tín hiệu mạnh rằng mã đó nên được quản lý như thuộc tính thay đổi được.

### 2.2. Những lý do mã nghiệp vụ thay đổi

| Loại thay đổi | Ví dụ | Vấn đề cần xác định |
|---|---|---|
| Sửa lỗi nhập liệu | USB-C-O1 thành USB-C-01 | Có giữ cùng danh tính? |
| Chuẩn hóa mã | SKU cũ chuyển sang chuẩn mã mới | Có giữ lịch sử mã cũ? |
| Đổi tổ chức | Sáp nhập phòng ban, thay mã chi nhánh | Phạm vi duy nhất thay đổi ra sao? |
| Đối tác thay định danh | Supplier đổi mã mặt hàng | Hệ thống có kiểm soát mã này không? |
| Tái sử dụng | Mã đã ngừng cấp lại cho đối tượng mới | Làm thế nào tra được dữ liệu lịch sử? |
| Đổi thứ tự | Dòng đơn hàng bị kéo thả | Thứ tự trình bày có phải định danh? |

Nếu mã có thể tái sử dụng theo thời gian, một mã duy nhất có thể chỉ đến nhiều thực thể ở các giai đoạn khác nhau. Khi đó, business key đơn lẻ không đủ làm định danh lịch sử bền vững.

## 3. JPA định danh entity như thế nào?

Trong persistence context, JPA nhận diện một entity qua **loại entity và giá trị primary key**. Với @EmbeddedId:

~~~java
ProductKey key = new ProductKey(42L, "USB-C-100");
CatalogProduct product = em.find(CatalogProduct.class, key);
~~~

Entity được quản lý dưới danh tính này. **JPA không cho phép ứng dụng thay đổi giá trị khóa chính sau khi entity đã trở thành persistent**; hành vi đổi primary key không được đặc tả để ứng dụng dựa vào. Đó là lý do không nên thiết kế một mã thường xuyên sửa được thành thành phần @Id.

Không nên dùng những cách sau để đổi ID của managed entity:

~~~java
// Ví dụ ý tưởng sai: đổi dữ liệu bên trong @EmbeddedId
// product.getId().setSku("CABLE-001");

// merge(), flush() hoặc detach() không tạo API JPA đổi PK chuẩn.
~~~

**merge()** sao chép trạng thái một entity sang đối tượng được quản lý theo định danh phù hợp; không phải lệnh đổi khóa cũ thành khóa mới. **flush()** đồng bộ trạng thái đang được quản lý; không biến việc sửa ID thành hợp lệ.

### 3.1. Khai báo khóa ghép bằng @EmbeddedId

~~~java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class ProductKey implements Serializable {

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    protected ProductKey() {}

    public ProductKey(Long tenantId, String sku) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.sku = Objects.requireNonNull(sku);
    }

    public Long getTenantId() { return tenantId; }
    public String getSku() { return sku; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductKey)) return false;
        ProductKey that = (ProductKey) other;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(sku, that.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }
}
~~~

Entity:

~~~java
package com.example.catalog;

import jakarta.persistence.*;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {
    @EmbeddedId
    private ProductKey id;

    @Column(name = "display_name", nullable = false, length = 180)
    private String displayName;

    protected CatalogProduct() {}

    public CatalogProduct(ProductKey id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public ProductKey getId() { return id; }
}
~~~

Trong mô hình này, ProductKey không có setter công khai nhằm giảm nguy cơ sửa định danh. Với field access, JPA vẫn có thể đọc/ghi các field theo mapping. Việc không tạo setter là một lựa chọn thiết kế API, không thay thế cho ràng buộc và kiểm soát nghiệp vụ.

**equals() và hashCode()** của lớp khóa phải dựa vào các thành phần định danh. Nếu một đối tượng ProductKey được đặt vào HashSet hoặc dùng làm khóa HashMap rồi bị sửa SKU, hashCode có thể đổi khiến việc tìm lại đối tượng thất bại. Đó là một chi phí khác của khóa mutable, ngay cả ngoài JPA.

### 3.2. @IdClass có giải quyết được không?

Một cách khác là đặt các trường @Id trực tiếp trên entity:

~~~java
@Entity
@IdClass(ProductId.class)
public class CatalogProduct {
    @Id
    private Long tenantId;

    @Id
    private String sku;

    private String displayName;

    protected CatalogProduct() {}
}
~~~

Lớp ProductId phải có các thành phần khóa tương ứng về tên và kiểu, Serializable cùng equals/hashCode phù hợp. Đây là một **biến thể thay thế** cho @EmbeddedId, không phải mã khai báo đồng thời với ví dụ trước.

Chọn @IdClass thay @EmbeddedId chỉ thay cách biểu diễn composite key; SKU nằm trong @Id vẫn mang rủi ro đổi danh tính khi nghiệp vụ sửa mã.

## 4. Chi phí ở database: khóa ngoại lan truyền

Một bảng cha có thể được tham chiếu bởi nhiều bảng con. Nếu PRIMARY KEY gồm (tenant_id, sku), các khóa ngoại cũng thường phải chứa đủ hai thành phần.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE catalog_products (
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    display_name VARCHAR(180) NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_tenant_id BIGINT NOT NULL,
    product_sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_tenant_id, product_sku)
        REFERENCES catalog_products (tenant_id, sku)
);
~~~

Quan hệ:

~~~text
catalog_products                      order_lines
(42, "USB-C-100")  <--------------  (42, "USB-C-100")
   PRIMARY KEY                         FOREIGN KEY
~~~

Nếu sửa SKU ở bảng cha, khóa ngoại có thể mất đích. DB có thể từ chối lệnh UPDATE nếu FK không hỗ trợ cập nhật khóa cha đang được tham chiếu. Cập nhật hàng con trước cũng có thể bị từ chối vì giá trị mới chưa có ở bảng cha. Do đó, đây không còn là một phép cập nhật cột đơn giản mà là **bài toán duy trì toàn vẹn tham chiếu**.

### 4.1. ON UPDATE CASCADE có phải lời giải toàn diện?

Một số DBMS cho phép:

~~~sql
CONSTRAINT fk_order_line_product
    FOREIGN KEY (product_tenant_id, product_sku)
    REFERENCES catalog_products (tenant_id, sku)
    ON UPDATE CASCADE
~~~

Khi được hỗ trợ và schema cấu hình đúng, DB sẽ chuyển khóa ngoại của những hàng con liên quan khi khóa cha thay đổi trong transaction. Nhưng cần lưu ý:

- Không phải mọi DBMS và loại ràng buộc đều hỗ trợ giống nhau.
- Một thay đổi trên cha có thể gây nhiều UPDATE con, thêm lock, index maintenance, transaction log và tải I/O.
- Nếu foreign key của con đồng thời là một phần primary key của chính con, cascade sẽ làm thay đổi danh tính các hàng con.
- Các EntityManager đang quản lý entity theo ID cũ, cache cấp hai hoặc hệ thống khác không tự biết đầy đủ cập nhật khóa do DB thực hiện.
- Trigger, vòng FK và dữ liệu lịch sử có thể khiến thao tác phức tạp hơn.

**ON UPDATE CASCADE là khả năng của database**, không biến việc sửa @EmbeddedId của managed entity thành hành vi JPA được định nghĩa.

### 4.2. Độ rộng khóa và index

Một composite key BIGINT + VARCHAR(40) thường rộng hơn một BIGINT. Khi nhiều bảng phải lưu cùng khóa ngoại, có thể tăng số cột, kích thước index và điều kiện JOIN. Đổi một thành phần khóa có thể làm nhiều index/FK được cập nhật.

Tuy vậy, chuyển sang surrogate key cũng có chi phí: bảng cha cần một ID và index PRIMARY KEY, trong khi business key vẫn có thể cần UNIQUE index. Do đó không thể khẳng định surrogate key luôn sử dụng ít bộ nhớ hoặc nhanh hơn. Cần xét **toàn bộ đồ thị bảng**, khối lượng ghi, độ rộng dữ liệu và truy vấn thực tế.

## 5. Chi phí trong JPA, persistence context và cache

### 5.1. Mapping khóa ngoại ghép

Khi một entity tham chiếu CatalogProduct có khóa (tenant_id, sku), quan hệ phải mô tả cả hai cột:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(
            name = "product_tenant_id",
            referencedColumnName = "tenant_id",
            nullable = false
        ),
        @JoinColumn(
            name = "product_sku",
            referencedColumnName = "sku",
            nullable = false
        )
    })
    private CatalogProduct product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}
}
~~~

Thay đổi khóa cha có thể đòi hỏi sửa mapping ở nhiều entity khác cùng các truy vấn SQL và DTO. Nếu còn dùng **@MapsId** để đưa khóa ngoại vào định danh entity con, thay khóa cha có thể kéo theo thay khóa chính của hàng con; sự phụ thuộc còn chặt hơn.

### 5.2. Persistence context

Một EntityManager đã tải CatalogProduct theo ProductKey cũ sẽ quản lý entity đó dưới định danh cũ. Nếu một SQL migration bên ngoài sửa khóa, trạng thái trong context không tự biến thành ID mới. Các thao tác tìm lại, refresh, merge, truy cập lazy relationship có thể gặp dữ liệu cũ hoặc lỗi khi bản ghi dưới ID cũ không còn tồn tại.

Không dùng SQL bulk đổi khóa rồi tiếp tục thao tác trên các managed entity với giả định rằng provider đã tự cập nhật identity map. Việc chuyển đổi cần điều phối transaction, vòng đời EntityManager và dữ liệu liên quan.

### 5.3. Cache và dữ liệu dẫn xuất

Rủi ro có thể lan tới:

- Cache cấp một của persistence context.
- Cache cấp hai và query cache do provider quản lý, nếu bật.
- Cache Redis hoặc bộ nhớ của service.
- Search index và dữ liệu báo cáo.
- Event đã gửi, ETL, CDC và kho dữ liệu ngoài.

Làm mới một context bằng clear() chỉ tác động các entity managed trong context đó, **không tự vô hiệu hóa mọi cache phân tán**. Nếu khóa nghiệp vụ trở thành thuộc tính thường còn ID ổn định, việc thay mã vẫn phải cập nhật dữ liệu dẫn xuất nhưng ít gây biến động ở các tham chiếu theo ID.

## 6. Chi phí ở API và hệ thống tích hợp

Giả sử API công bố:

~~~http
GET /tenants/42/products/USB-C-100
PATCH /tenants/42/products/USB-C-100
~~~

Khi SKU đổi, đường dẫn cũ có thể không còn tìm thấy bản ghi. Link trong email, event cũ, tài liệu, hệ thống đối tác hoặc idempotency key có thể vẫn mang SKU cũ. Chuyển PK nội bộ sang ID kỹ thuật không tự khắc phục các phụ thuộc bên ngoài nếu API vẫn coi SKU là định danh vĩnh viễn.

Một thiết kế rõ ràng:

~~~text
productId   = định danh bất biến
tenantId    = phạm vi sở hữu
sku         = mã nghiệp vụ thay đổi được
displayName = tên hiển thị thay đổi được
~~~

API có thể tham chiếu theo ID:

~~~http
GET /products/{productId}
PATCH /products/{productId}
~~~

và tra theo mã:

~~~http
GET /tenants/42/products?sku=USB-C-100
~~~

Nếu cần tra cứu theo mã cũ, có thể bổ sung bảng **product_code_history** hoặc **business_key_aliases** liên kết mã, khoảng thời gian hiệu lực, tenant và productId. Cần quy định mã cũ có được tái sử dụng không, mỗi mã có thể trỏ nhiều đối tượng theo thời gian không, và event cũ cần mốc thời gian để phân giải ID không.

### 6.1. Sửa mã và đổi danh tính là hai nghiệp vụ khác nhau

| Tình huống | Có thể là cùng thực thể? | Điểm cần quyết định |
|---|---|---|
| Sửa SKU nhập sai | Có | Có lưu alias cho mã sai không? |
| Đổi chuẩn SKU | Có | Những consumer cũ cập nhật ra sao? |
| Gộp hai sản phẩm | Không đơn giản | Giữ ID nào, di chuyển tham chiếu nào? |
| Chuyển sang tenant khác | Tùy domain | Là chuyển quyền sở hữu hay tạo entity mới? |
| Tái sử dụng SKU đã ngừng | Thường khác thực thể | Cần ID hoặc thời điểm để tránh nhầm |

Nếu chuyển tenant là nghiệp vụ có tác động đến quyền truy cập, dùng surrogate ID vẫn cần ràng buộc và authorization ngăn tham chiếu chéo tenant sai quyền.

## 7. Mô hình ước lượng chi phí bảo trì

Có thể chia chi phí vòng đời thành phần xây dựng ban đầu, vận hành thường xuyên và những lần phải đổi mã:

\[
C_{\text{vòng đời}} =
C_{\text{khởi tạo}} +
C_{\text{vận hành}} +
\sum_i N_i \times C_{\text{thay đổi}, i}
\]

Trong đó:

- \(C_{\text{khởi tạo}}\): thiết kế schema, mapping JPA và code ban đầu.
- \(C_{\text{vận hành}}\): chi phí lưu trữ, index, JOIN, monitoring, truy vấn và bảo trì thông thường.
- \(N_i\): số lần dự kiến xảy ra loại thay đổi thứ i trong giai đoạn đánh giá.
- \(C_{\text{thay đổi}, i}\): công sức, rủi ro và ảnh hưởng của mỗi lần thay đổi tương ứng.

Mô hình này chỉ là **công cụ so sánh kiến trúc**, không phải công thức chi phí chuẩn do JPA cung cấp. Nếu không có dữ liệu lịch sử, có thể dùng mức **thấp / trung bình / cao** thay vì tạo ra những xác suất giả định thiếu căn cứ.

### 7.1. Phân rã chi phí một lần đổi business key

| Hạng mục | Business key nằm trong composite PK | Surrogate PK và UNIQUE business key |
|---|---|---|
| Thêm một cột ID riêng lúc thiết kế | Không cần | Cần |
| Giữ tính duy nhất của mã | Có thể do PK bảo vệ | Cần UNIQUE riêng |
| Foreign key của bảng con | Có thể gồm nhiều cột | Thường trỏ vào một ID |
| Đổi mã hiện tại | Có thể làm đổi PK và các FK | Chủ yếu đổi thuộc tính nghiệp vụ |
| JPA entity identity | Bị tác động nếu thay khóa | Giữ ổn định khi đổi mã |
| Mapping phụ thuộc | Có thể liên quan @EmbeddedId, @IdClass, @MapsId | Ít phụ thuộc vào mã hơn |
| Cache theo ID | Có thể phải chuyển khóa và làm mới nhiều trạng thái | Cache key theo ID vẫn ổn định |
| API công bố mã như ID | Vẫn bị ảnh hưởng | Vẫn bị ảnh hưởng nếu API chưa đổi |
| Index ở bảng cha | Có thể ít hơn một index | Thường cần PK và UNIQUE index |
| Audit lịch sử | Dễ nhầm đổi mã với đổi danh tính | Dễ gắn mọi sự kiện với ID ổn định |
| Rủi ro migration trên nhiều bảng | Có thể cao | Thường thấp hơn ở quan hệ nội bộ |

Một ứng dụng chỉ có một bảng không có FK và chưa có consumer ngoài có thể ít chịu ảnh hưởng. Nhưng khi khóa được dùng trong hàng chục bảng và sự kiện tích hợp, **chi phí mỗi lần đổi mã** có thể trở thành phần chi phí lớn hơn chi phí xây dựng ban đầu.

### 7.2. Những câu hỏi thu thập dữ liệu thực tế

Trước khi chọn cấu trúc khóa, hãy điều tra:

1. **Ai sở hữu quy tắc mã?** Công ty, đối tác, khách hàng hay cơ quan bên ngoài?
2. **Bao nhiêu lần mã đã thay đổi?** Có ticket sửa mã, migration hoặc kế hoạch đổi chuẩn không?
3. **Mã duy nhất trong phạm vi nào?** Toàn cục, theo tenant, theo tổ chức, trạng thái hay khoảng thời gian?
4. **Mã có được tái sử dụng?** Bản ghi cũ ngừng hoạt động có nhường mã cho bản ghi mới không?
5. **Bao nhiêu bảng tham chiếu?** Bao gồm khóa ngoại trực tiếp, khóa ghép ở bảng con và bảng trung gian.
6. **Bao nhiêu lớp JPA phụ thuộc?** Entity dùng @EmbeddedId, @IdClass, @MapsId và @JoinColumns.
7. **Bao nhiêu hệ thống ngoài phụ thuộc?** API, event, ETL, report, cache, data warehouse, search index.
8. **Có yêu cầu vận hành liên tục không?** Có thể khóa bảng/dừng ghi trong lúc đổi mã hay cần rolling deployment?
9. **Có quy trình rollback và audit không?** Có thể biết bản ghi trước và sau đổi mã là cùng thực thể không?
10. **Các truy vấn nào quan trọng?** Phần lớn tìm bằng SKU hay bằng ID, và cần index nào cho mỗi đường truy vấn?

Một bảng quyết định hữu ích có thể ghi rõ lý do:

| Tiêu chí | Ví dụ kết quả khảo sát |
|---|---|
| Khóa ứng viên | tenant_id + sku |
| Tính bất biến | Không; có quy trình đổi SKU |
| Số bảng tham chiếu | Nhiều bảng đơn hàng, tồn kho, bảo hành |
| API bên ngoài | Có dùng SKU trong URL và event |
| Cần giữ lịch sử mã | Có |
| Phương án đề xuất | product_id bất biến, UNIQUE(tenant_id, sku), bảng lịch sử mã |
| Điều kiện còn phải quyết định | Tái sử dụng SKU và thời hạn alias |

Nếu mã chưa từng đổi, điều đó **không tự chứng minh** nó sẽ không thể đổi. Cần xem hợp đồng nghiệp vụ và chính sách tương lai, không chỉ tập dữ liệu lịch sử.

## 8. So sánh hai thiết kế quan hệ

### 8.1. Phương án A: PRIMARY KEY (tenant_id, sku)

~~~sql
CREATE TABLE catalog_products (
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    display_name VARCHAR(180) NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_tenant_id BIGINT NOT NULL,
    product_sku VARCHAR(40) NOT NULL,
    FOREIGN KEY (product_tenant_id, product_sku)
        REFERENCES catalog_products (tenant_id, sku)
);
~~~

Ưu điểm: PRIMARY KEY diễn đạt trực tiếp quy tắc duy nhất hiện tại; không cần tạo product_id riêng. Nhược điểm: khi SKU thay đổi, phải có cách đảm bảo các khóa ngoại, entity identity và dữ liệu trong cache không bị mâu thuẫn.

### 8.2. Phương án B: product_id làm PK, business key làm UNIQUE

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(40) NOT NULL,
    display_name VARCHAR(180) NOT NULL,
    CONSTRAINT uk_product_tenant_sku UNIQUE (tenant_id, sku)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    CONSTRAINT fk_order_line_product_id
        FOREIGN KEY (product_id)
        REFERENCES catalog_products (product_id)
);
~~~

Đổi SKU có thể được biểu diễn như cập nhật thuộc tính nghiệp vụ:

~~~sql
UPDATE catalog_products
SET sku = 'CABLE-001'
WHERE product_id = 1001
  AND tenant_id = 42
  AND sku = 'USB-C-100';
~~~

Khóa ngoại order_lines.product_id vẫn giữ **1001**, không cần đổi để tiếp tục tham chiếu cùng sản phẩm. UNIQUE(tenant_id, sku) vẫn bảo vệ quy tắc không trùng mã trong tenant.

Đổi sang phương án B làm phát sinh index/ID kỹ thuật và cần cơ chế cấp khóa. Chi phí này phải được cân đối với việc giảm cập nhật dây chuyền trên các bảng tham chiếu và giảm rủi ro đổi định danh của managed entity.

## 9. Thiết kế JPA với surrogate ID bất biến

Ví dụ sau là **một phương án thay thế** cho entity CatalogProduct dùng @EmbeddedId ở phần trước. Dự án chỉ chọn một trong hai mapping cho cùng persistence unit.

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "catalog_products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "product_id", nullable = false, updatable = false)
    private Long id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private Long tenantId;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    @Column(name = "display_name", nullable = false, length = 180)
    private String displayName;

    @Version
    private long version;

    protected CatalogProduct() {}

    public CatalogProduct(Long tenantId, String sku, String displayName) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.sku = Objects.requireNonNull(sku);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }

    public void renameSku(String newSku) {
        if (newSku == null || newSku.isBlank() || newSku.length() > 40) {
            throw new IllegalArgumentException("Invalid SKU");
        }
        this.sku = newSku;
    }
}
~~~

Các điểm đáng chú ý:

- **id** là khóa chính bất biến và không có setter công khai.
- **tenantId** được xem là không thay đổi trong mô hình minh họa; chuyển tenant là quyết định domain riêng.
- **sku** là thuộc tính thường có thể đổi qua nghiệp vụ renameSku().
- **@Version** giúp JPA nhận diện một số xung đột cập nhật lạc quan khi đồng bộ entity.
- **@UniqueConstraint** biểu đạt tính duy nhất của mã trong tenant; ở DB đã có sẵn phải bảo đảm ràng buộc thực sự được triển khai bằng DDL/migration.
- **String.isBlank()** cần Java 11 hoặc mới hơn; với Java cũ dùng cách kiểm tra chuỗi tương đương.

Nếu đang dùng database không hỗ trợ kiểu identity theo mapping/DDL đã chọn, có thể thay bằng một chiến lược sinh ID khác được provider hỗ trợ. Điều đó không thay đổi lập luận về **tính ổn định của định danh**.

Quan hệ tới sản phẩm giờ có thể dùng một khóa ngoại:

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private CatalogProduct product;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}
}
~~~

Khi CatalogProduct thay SKU, quan hệ OrderLine.product vẫn trỏ đến cùng ID. Nếu một dòng đơn hàng cần ghi nhớ **SKU tại thời điểm bán**, nên lưu một trường snapshot riêng; SKU hiện tại của sản phẩm không phải giá trị lịch sử bất biến.

### 9.1. Cập nhật business key bên trong transaction

Ví dụ dùng Spring transaction:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCodeService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void rename(Long productId, String newSku) {
        CatalogProduct product = em.find(CatalogProduct.class, productId);
        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        product.renameSku(newSku);
        // Dirty checking sẽ đồng bộ cột sku khi flush/commit.
        // Khóa product_id và các FK theo product_id không thay đổi.
    }
}
~~~

Ví dụ này giả định Spring đã cấu hình EntityManager và transaction manager đúng cách. Trong môi trường Jakarta EE, có thể dùng **jakarta.transaction.Transactional** và cơ chế JTA container tương ứng. Không nên nhầm hai annotation có tên gần giống là cùng cơ chế quản lý transaction.

Nếu hai request cố đổi hai sản phẩm trong cùng tenant sang một SKU, **UNIQUE constraint ở database** là cơ chế bảo vệ cuối cùng. Chỉ chạy SELECT kiểm tra trước UPDATE không ngăn được tình huống race condition. Khi phát sinh lỗi unique hoặc optimistic locking, service cần xử lý theo chính sách nghiệp vụ thay vì retry mù.

## 10. Khi nào composite key vẫn có thể hợp lý?

Không nên suy diễn rằng mọi khóa ghép đều là thiết kế xấu. Vấn đề trọng tâm là **các thành phần có bất biến và đại diện đúng danh tính không**.

### 10.1. Bảng liên kết hai entity có ID bất biến

~~~sql
CREATE TABLE student_course_enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);
~~~

Nếu nghiệp vụ xác định một sinh viên có tối đa một quan hệ đăng ký với mỗi khóa học, và cả student_id lẫn course_id đều là ID kỹ thuật không đổi, composite PK có thể thể hiện chính xác danh tính quan hệ. Nếu cần nhiều lượt đăng ký lại và lưu lịch sử, phải xem lại cấu trúc khóa.

### 10.2. Dòng có định danh nội bộ bất biến

Một dòng chứng từ có thể được định danh bằng **(document_id, immutable_line_id)** nếu cả hai giá trị được cấp một lần và không đổi. Ngược lại, **(document_id, display_order)** không ổn định nếu người dùng có thể kéo thả thứ tự hiển thị. Có thể giữ line_id làm thành phần khóa và display_order là thuộc tính sửa được.

### 10.3. Multitenancy

Trong hệ đa tenant, **(tenant_id, local_record_id)** có thể là khóa ghép hợp lệ khi local_record_id chỉ duy nhất bên trong tenant và mỗi thành phần ổn định. Nếu dùng surrogate ID duy nhất toàn cục, vẫn có thể cần composite unique/FK hoặc ràng buộc truy cập để đảm bảo quan hệ không tham chiếu chéo tenant trái phép.

Một lựa chọn ID kỹ thuật không tự loại bỏ yêu cầu cách ly dữ liệu và phân quyền của kiến trúc multi-tenant.

## 11. Di chuyển từ composite business PK sang surrogate PK

Hệ thống legacy có thể đang sử dụng:

~~~text
catalog_products PRIMARY KEY (tenant_id, sku)
order_lines FOREIGN KEY (product_tenant_id, product_sku)
~~~

và muốn chuyển thành:

~~~text
catalog_products PRIMARY KEY (product_id)
catalog_products UNIQUE (tenant_id, sku)
order_lines FOREIGN KEY (product_id)
~~~

Đây là **migration thay đổi định danh**, cần triển khai thành các pha có kiểm soát. Không thể hoàn thành chỉ bằng việc sửa @EmbeddedId thành @Id trong Java.

### 11.1. Pha khảo sát

Xác định toàn bộ bảng tham chiếu trực tiếp/gián tiếp, khóa ngoại nằm trong primary key bảng con, stored procedure, trigger, view, ETL, event, API, query native, cache và ứng dụng đang sử dụng bộ khóa cũ. Tìm dữ liệu mồ côi, mã trùng hoặc quy tắc mã thiếu nhất quán trước khi backfill.

### 11.2. Pha mở rộng schema

Thêm cột **product_id** vào bảng sản phẩm, cấp một ID duy nhất cho từng hàng và tạo các ràng buộc thích hợp. Chọn BIGINT/sequence, identity hay UUID theo DB và provider. Trong hệ đang có giao dịch ghi mới, cần cơ chế cấp product_id cho **cả hàng hiện hữu lẫn hàng mới** trong thời gian chuyển đổi.

Tiếp tục giữ composite key cũ làm khóa hợp lệ trong giai đoạn ứng dụng chưa được chuyển hoàn toàn.

### 11.3. Pha chuyển bảng tham chiếu

Thêm product_id vào từng bảng con, rồi backfill bằng JOIN theo khóa cũ. Ví dụ SQL theo cú pháp PostgreSQL:

~~~sql
-- Giả định đã thêm cột product_id vào cả hai bảng.
UPDATE order_lines AS ol
SET product_id = p.product_id
FROM catalog_products AS p
WHERE ol.product_tenant_id = p.tenant_id
  AND ol.product_sku = p.sku;
~~~

Đối chiếu các hàng con có product_id chưa được điền, xem lại dữ liệu mồ côi và xây index/FK mới. Trong khi có các phiên bản ứng dụng cũ và mới cùng chạy, phải duy trì tính nhất quán của cả hai kiểu tham chiếu. Không được bỏ cột cũ nếu ứng dụng cũ còn ghi vào đó.

### 11.4. Pha đổi mapping và ràng buộc

Chuyển entity, repository, service, query và giao thức cần thiết sang product_id. Thay @EmbeddedId hoặc @IdClass ở CatalogProduct bằng @Id ổn định, giữ UNIQUE(tenant_id, sku). Khi mọi consumer đều dùng cấu trúc mới, đổi PRIMARY KEY/FK thật ở DB và gỡ phụ thuộc cũ.

Tạo index hoặc đổi PRIMARY KEY trên bảng lớn có thể gây lock đáng kể; nên lựa chọn thời điểm và công cụ migration theo khả năng online DDL của DBMS, kích thước dữ liệu và yêu cầu uptime.

### 11.5. Pha làm mới các hệ thống liên quan

Xử lý các EntityManager còn giữ ID cũ, cache cấp hai, cache ứng dụng, index tìm kiếm và consumer CDC/event. Nếu còn khách hàng dùng URL chứa SKU, duy trì mapping mã cũ sang productId hoặc phiên bản API tương thích theo hợp đồng đã chốt.

Migration nhiều pha cần nguồn lực đáng kể. **Đó là một phần khoản nợ bảo trì** cần tính ngay từ lúc chọn business key thay đổi được làm PK.

## 12. Đổi mã khi chưa thể migration

Với schema legacy, một thay đổi business key có thể được coi là **quy trình chuyển định danh** gồm:

1. Xác định bản ghi cũ và mới có đúng là cùng một thực thể về mặt nghiệp vụ không.
2. Xác nhận mã mới không xung đột, và người thao tác có quyền đổi mã.
3. Lập kế hoạch cập nhật parent/child theo foreign key, transaction, trigger, khóa DB và khả năng ON UPDATE CASCADE.
4. Điều phối persistence context, cache, index, event, API và consumer ngoài.
5. Lưu audit và phương án phục hồi khi một bước lỗi.

Nếu không có ON UPDATE CASCADE hoặc constraint cho phép cập nhật theo trình tự thích hợp, không nên tự giả định UPDATE bảng con trước hay bảng cha trước sẽ thành công. Có thể cần tạo hàng mới rồi chuyển tham chiếu có kiểm soát, dùng constraint phù hợp hoặc migration nhiều giai đoạn. Chi tiết phụ thuộc schema và DBMS.

**Không sửa trực tiếp trường @EmbeddedId của entity đang managed** để thực hiện quy trình này. Thao tác đó dựa vào hành vi JPA không được bảo đảm.

### 12.1. Giới hạn của rollback

Một DB transaction có thể rollback thay đổi trong phạm vi giao dịch của DB đó. Nhưng email đã gửi, HTTP request đã hoàn tất, Kafka event đã được consumer xử lý hoặc search index đã đổi sẽ không tự quay về chỉ vì DB rollback. Khi phải đồng bộ nhiều hệ thống, có thể cần transactional outbox, event chứa ID ổn định, idempotency và cơ chế xử lý bù trừ.

## 13. Lịch sử mã và uniqueness theo thời gian

Một business key có thể trải qua nhiều đời:

~~~text
product_id | tenant_id | sku         | valid_from | valid_to
-----------+-----------+-------------+------------+---------
1001       | 42        | USB-C-100   | 2024-01-01 | 2025-05-01
1001       | 42        | CABLE-001   | 2025-05-01 | 2026-03-01
1001       | 42        | CABLE-01-B  | 2026-03-01 | null
~~~

Đây là một mô hình minh họa. Khi triển khai thực tế cần xác định giá trị hiệu lực đầu/cuối, khả năng khoảng thời gian giao nhau, quyền sửa lịch sử và tính duy nhất của mã ở mỗi thời điểm.

Nếu SKU có thể được tái sử dụng cho sản phẩm mới sau khi sản phẩm cũ ngừng bán, một event lịch sử chỉ có SKU sẽ không đủ để xác định đúng sản phẩm. ID ổn định hoặc tổ hợp mã và thời điểm hiệu lực có thể cần xuất hiện trong giao thức trao đổi.

### 13.1. Chuẩn hóa business key

Những chuỗi sau có thể được nghiệp vụ xem như cùng một mã:

~~~text
"ABC-01"
"abc-01"
"ABC-01 "
~~~

Collation, quy tắc trim, chữ hoa/thường và encoding ảnh hưởng tới uniqueness. Có thể cần chuẩn hóa tại ứng dụng, functional unique index hoặc normalized column tại DB. **@UniqueConstraint** thông thường trên hai cột không tự diễn tả mọi quy tắc canonicalization.

Việc thường xuyên phải sửa định dạng mã là một lý do bổ sung để tránh dùng chính chuỗi đó làm khóa bền vững.

## 14. Hiệu năng: cần đo trên workload thật

Surrogate key thường giảm số cột trong FK của bảng con, nhưng cũng thêm ID/index ở bảng cha. Khi đánh giá phải xét:

- Kích thước BIGINT so với UUID hoặc tổ hợp BIGINT + VARCHAR.
- Index của PRIMARY KEY và UNIQUE business key.
- JOIN một cột hay nhiều cột, mức độ chọn lọc và thứ tự index.
- Tần suất ghi/đổi mã, lượng row cần cascade.
- Partitioning, multitenancy, index locality và cache page.
- Tỉ lệ truy vấn theo productId so với theo SKU.

Nếu phần lớn truy vấn tìm theo SKU, vẫn cần index business key phù hợp dù PK là productId. Không nên tuyên bố thiết kế surrogate nhanh hơn một tỉ lệ cố định mà không đo DB, dữ liệu và truy vấn cụ thể.

## 15. Những lỗi thiết kế thường gặp

### 15.1. Lấy “đang duy nhất” làm bằng chứng “không bao giờ đổi”

Một business key có thể duy nhất ở thời điểm hiện tại nhưng vẫn đổi do sửa lỗi, tái cấu trúc doanh nghiệp hoặc thay chuẩn mã. Cần hợp đồng bất biến từ nghiệp vụ.

### 15.2. Dùng setter sửa @EmbeddedId rồi gọi merge()

JPA không định nghĩa việc thay primary key của managed entity như một cập nhật thuộc tính thông thường. Merge không phải lệnh đổi khóa. Hãy thiết kế định danh ổn định hoặc kế hoạch migration riêng.

### 15.3. Chuyển sang surrogate PK nhưng bỏ UNIQUE business key

Nếu trước đây PK (tenant_id, sku) ngăn trùng mã, sau khi chuyển sang product_id vẫn phải có UNIQUE(tenant_id, sku) hoặc cơ chế tương ứng theo quy tắc nghiệp vụ. SELECT kiểm tra trước INSERT không đủ bảo vệ đồng thời.

### 15.4. Tin rằng ON UPDATE CASCADE làm mới toàn hệ thống

Cascade chỉ giúp ràng buộc DB được cấu hình phù hợp. JPA context, cache, API và event ngoài DB không tự đổi khóa đồng bộ.

### 15.5. Dùng số thứ tự hiển thị làm một phần ID

Nếu người dùng thay thứ tự dòng, display_order hoặc line_number không nên là một thành phần định danh bền vững. Có thể giữ line_id riêng.

### 15.6. Xóa và tạo lại bản ghi để đổi mã

Xóa bản ghi cũ có thể bị FK chặn, kích hoạt cascade xóa hoặc làm mất danh tính mà audit và đối tác đang dùng. Tạo bản ghi mới chỉ phù hợp khi nghiệp vụ thật sự xem đó là một thực thể khác hoặc đã thiết kế chuyển tham chiếu đầy đủ.

### 15.7. Đổi PK trong DB nhưng vẫn dùng cache/JPA cũ

Các EntityManager và cache có thể còn tham chiếu ID cũ. Khi migration cần quy trình kết thúc phiên, invalidation và làm mới dữ liệu theo cách được provider hỗ trợ.

### 15.8. Không tính chi phí giao thức ngoài

Dù DB đã dùng surrogate PK, nếu API và event vẫn công bố mã thay đổi được như ID vĩnh viễn thì lỗi tương thích vẫn có thể xảy ra. Cần quyết định external ID ổn định và cách tra mã cũ.

## 16. Bài tập áp dụng

### Bài 1: Nhân viên đổi mã sau sáp nhập

Schema gồm employees PK(company_id, employee_code), timesheets FK(company_id, employee_code) và payrolls FK(company_id, employee_code). Sau sáp nhập phòng ban, một nhân viên nhận mã mới nhưng vẫn là cùng một người.

**Câu hỏi:** Có nên sửa employee_code trong @EmbeddedId?

**Gợi ý:** Không nên đổi ID của managed entity bằng setter. Hãy xét chi phí chuyển các FK, mapping JPA, cache, báo cáo và audit. Một employee_id bất biến cùng unique constraint trên mã nghiệp vụ có thể làm mô hình dễ bảo trì hơn.

### Bài 2: Sắp xếp lại dòng đơn hàng

OrderLine dùng PRIMARY KEY(order_id, line_number), nhưng UI cho phép kéo thả đổi thứ tự.

**Câu hỏi:** line_number có ổn định không?

**Gợi ý:** Nếu đó là thứ tự trình bày, nó không nên là thành phần ID. Cân nhắc line_id bất biến và display_order riêng. Nếu số dòng được cấp cố định theo hợp đồng nghiệp vụ, có thể đánh giá composite key theo ngữ nghĩa khác.

### Bài 3: Bảng nối có hai ID kỹ thuật

Permission có PRIMARY KEY(user_id, resource_id); cả hai ID đều bất biến và một cặp chỉ tồn tại một lần.

**Câu hỏi:** Có bắt buộc tạo permission_id mới?

**Gợi ý:** Không. Composite PK có thể đúng khi định danh của bản ghi chính là cặp quan hệ ổn định. Nhưng nếu muốn lưu nhiều lần cấp quyền lịch sử cho cùng cặp, cần xem lại cấu trúc khóa.

### Bài 4: Đánh giá khoản nợ bảo trì

Hệ thống có 40 bảng FK theo (tenant_id, sku), 6 dịch vụ phát/nhận mã đó trong event, và nghiệp vụ đổi chuẩn SKU hằng năm.

**Câu hỏi:** Ngoài UPDATE trên bảng sản phẩm còn phải tính những khoản nào?

**Gợi ý:** Cập nhật FK, transaction lock, index, mapping JPA, cache, audit, API/event compatibility, CDC, consumer, migration, kiểm thử đồng thời và phương án phục hồi. So sánh với chi phí thêm product_id và UNIQUE(tenant_id, sku).

### Bài 5: Mất uniqueness khi chuyển PK

Nhóm phát triển đổi PK từ (tenant_id, sku) sang product_id nhưng không tạo UNIQUE cho mã và tenant.

**Câu hỏi:** Điều gì có thể sai?

**Gợi ý:** Hai sản phẩm có thể cùng SKU trong một tenant nếu không có constraint bảo vệ. Hai transaction đồng thời càng khiến việc chỉ kiểm tra ở Java không đáng tin cậy.

### Bài 6: SKU được tái sử dụng

Mã A1 thuộc sản phẩm P1 trước năm 2025, rồi được cấp lại cho P2 năm 2026. Một event từ năm 2024 chỉ chứa sku=A1.

**Câu hỏi:** Vì sao không thể tra event theo SKU hiện tại?

**Gợi ý:** Cùng một mã có thể chỉ hai thực thể khác nhau ở hai thời điểm. Cần ID ổn định hoặc thông tin thời điểm cùng bảng lịch sử ánh xạ mã.

## 17. Bảng quyết định nhanh

| Tình huống | Hướng thiết kế thường phù hợp |
|---|---|
| Khóa chứa mã có thể sửa | PK kỹ thuật bất biến, UNIQUE business key |
| Khóa chứa email, username hoặc số điện thoại | Không mặc định dùng làm PRIMARY KEY |
| Khóa ghép gồm hai ID bất biến của bảng liên kết | Có thể giữ composite PK |
| Mã nghiệp vụ có lịch sử thay đổi | ID ổn định và lịch sử mã/alias khi cần |
| Nhiều FK và nhiều consumer ngoài | Ưu tiên ID ổn định và giao thức trao đổi rõ |
| Legacy schema đang có mutable composite PK | Migration nhiều pha hoặc quy trình đổi khóa có kiểm soát |
| Mã chỉ duy nhất trong tenant | Giữ quy tắc unique và phân quyền đúng phạm vi |
| Mã bất biến theo hợp đồng domain | Composite PK có thể hợp lý nếu mọi thành phần ổn định |

## 18. Kết luận

Đánh giá khóa ghép phải bắt đầu từ **khả năng thay đổi của từng thành phần khóa**, sau đó mới chọn cú pháp @EmbeddedId hoặc @IdClass. Nếu business key có thể đổi, việc đặt nó trong PRIMARY KEY biến yêu cầu sửa mã thành thay đổi định danh và có thể lan tới **khóa ngoại, persistence context, cache, API, event, audit và migration**.

Đối với mã nghiệp vụ có thể thay đổi, một phương án thường giảm chi phí vòng đời là **khóa chính kỹ thuật bất biến**, đồng thời giữ quy tắc duy nhất bằng **UNIQUE constraint** và lưu lịch sử mã nếu nghiệp vụ cần. Composite key vẫn phù hợp khi các thành phần phản ánh đúng định danh và thật sự bất biến.

Quyết định nên so sánh **chi phí tạo mô hình ban đầu** với **số lần đổi mã và chi phí mỗi lần trên toàn hệ thống**. Một khóa được chọn tốt phải duy trì được danh tính dữ liệu ổn định qua những thay đổi nghiệp vụ có thể dự báo.
