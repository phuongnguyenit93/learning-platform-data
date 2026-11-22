# Cấu hình bảng tập hợp bằng @CollectionTable

## 1. Bài toán: lưu một tập hợp giá trị thuộc về Entity

Một entity thường có các thuộc tính đơn giản như tên, trạng thái hoặc ngày tạo. Nhưng trong nghiệp vụ, một entity cũng có thể sở hữu nhiều giá trị cùng loại: danh sách số điện thoại, nhãn sản phẩm, kỹ năng của nhân viên, các địa chỉ giao hàng hoặc các cặp thuộc tính tùy chỉnh.

Nếu mỗi giá trị không có định danh và vòng đời độc lập, việc tạo một entity riêng cho từng giá trị có thể làm mô hình phức tạp không cần thiết. Jakarta Persistence cung cấp @ElementCollection để ánh xạ tập hợp basic type hoặc embeddable type. Các phần tử của tập hợp được lưu trong một bảng riêng gọi là collection table. Annotation @CollectionTable xác định bảng đó và cách nó liên kết về entity sở hữu.

Ví dụ, một Customer có nhiều tag. Bảng customer lưu thông tin khách hàng; bảng customer_tag lưu các tag và khóa ngoại trỏ về customer. Mỗi tag là một value thuộc về Customer, không phải một entity độc lập.

Bài này giải thích:
- Khi nào dùng @ElementCollection và @CollectionTable.
- Cách cấu hình tên bảng, join column và constraint.
- Cách ánh xạ collection basic, enum, embeddable và map.
- Cách quản lý thứ tự, truy vấn, tải dữ liệu và kiểm thử.
- Khi nào nên chuyển sang @OneToMany thay vì collection table.

## 2. Phân biệt Entity collection và Element collection

Trước khi cấu hình bảng, cần xác định phần tử có phải entity hay chỉ là value.

### 2.1. Element collection

Dùng @ElementCollection khi các phần tử:
- Không có định danh JPA riêng.
- Không được truy vấn hoặc quản lý như một entity độc lập.
- Có vòng đời gắn với entity sở hữu.
- Là basic type hoặc embeddable type.

Ví dụ:
- Một Customer có tập hợp tag dạng String.
- Một User có tập hợp role dạng enum.
- Một Product có nhiều cặp thuộc tính dạng key/value.
- Một Person có danh sách các đối tượng ContactAddress được đánh dấu @Embeddable.

Các phần tử được lưu trong collection table. Mỗi hàng thường chứa khóa ngoại về entity chủ và các cột biểu diễn giá trị phần tử.

### 2.2. One-to-many

Dùng @OneToMany khi phần tử là entity có định danh và vòng đời riêng. Ví dụ Order có các OrderLine; mỗi dòng hàng có thể có ID, trạng thái, quan hệ hoặc được tham chiếu bởi nghiệp vụ khác.

Không nên chọn @ElementCollection chỉ vì muốn tránh khai báo entity. Nếu một phần tử cần được tải, cập nhật, phân quyền hoặc tham chiếu độc lập, hãy cân nhắc entity riêng.

| Tiêu chí | @ElementCollection | @OneToMany |
|---|---|---|
| Kiểu phần tử | Basic hoặc embeddable | Entity |
| Định danh riêng | Không có entity identity | Có @Id riêng |
| Vòng đời | Gắn với entity sở hữu | Có thể độc lập tùy mô hình |
| Repository riêng | Không | Có thể có |
| Bảng lưu trữ | Collection table | Bảng entity con |
| Quan hệ entity | Không phải entity relationship | Có quan hệ entity |
| Use case điển hình | Tag, role, value object, thuộc tính phụ | OrderLine, InvoiceItem, Comment |

Một value object có thể chứa nhiều field và vẫn là embeddable. Nhiều field không tự động biến nó thành entity; yếu tố quyết định là định danh và vòng đời nghiệp vụ.

## 3. Vai trò của @ElementCollection và @CollectionTable

Hai annotation thường đi cùng nhau:

- @ElementCollection khai báo thuộc tính là tập hợp basic hoặc embeddable values.
- @CollectionTable mô tả bảng lưu tập hợp và các cột nối bảng đó với entity sở hữu.

Ví dụ tối thiểu:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tag",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag", nullable = false, length = 80)
    private Set<String> tags = new LinkedHashSet<>();

    protected Customer() {
    }

    public Customer(Set<String> tags) {
        this.tags.addAll(tags);
    }

    public Long getId() {
        return id;
    }

    public Set<String> getTags() {
        return Collections.unmodifiableSet(tags);
    }

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Tag is required");
        }
        tags.add(tag);
    }

    public void removeTag(String tag) {
        tags.remove(tag);
    }
}
```

Trong ví dụ:
- Customer là entity sở hữu tập hợp.
- tags là element collection kiểu Set<String>.
- customer_tag là collection table.
- customer_id là join column trỏ về khóa chính của customer.
- tag là cột chứa giá trị String.

@CollectionTable không tự khai báo kiểu phần tử. Kiểu collection và cách lưu giá trị được xác định bởi @ElementCollection cùng @Column hoặc mapping embeddable.

Nếu không chỉ định @CollectionTable, provider có thể áp dụng quy tắc tên mặc định theo đặc tả. Trong ứng dụng thực tế, khai báo tên bảng và join column tường minh thường giúp schema dễ đọc, ổn định và dễ quản lý bằng migration hơn.

## 4. Cấu hình các thuộc tính của @CollectionTable

### 4.1. name

name xác định tên collection table:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Tên bảng nên phản ánh cả entity sở hữu và ý nghĩa tập hợp. Ví dụ customer_tag dễ hiểu hơn một tên chung như values.

### 4.2. joinColumns

joinColumns khai báo cột hoặc các cột khóa ngoại liên kết collection table với bảng entity sở hữu.

```java
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(
        name = "customer_id",
        referencedColumnName = "id"
    )
)
```

Trong đó:
- name là tên cột ở collection table.
- referencedColumnName là tên cột ở bảng được tham chiếu; nếu bỏ qua, provider mặc định tham chiếu khóa chính tương ứng của entity sở hữu.
- nullable, foreignKey và các thuộc tính khác của @JoinColumn có thể điều khiển chi tiết DDL khi provider sinh schema.

Nếu entity sở hữu dùng composite primary key, cần khai báo các join columns tương ứng với các thành phần khóa. Số lượng và thứ tự cột phải khớp với khóa được tham chiếu.

### 4.3. schema và catalog

Có thể chỉ định schema hoặc catalog khi collection table nằm trong vùng database cụ thể:

```java
@CollectionTable(
    name = "customer_tag",
    schema = "app_data",
    joinColumns = @JoinColumn(name = "customer_id")
)
```

Cách đặt schema nên thống nhất với cấu hình database và migration. Không nên để annotation, default schema của connection và script migration sử dụng các tên khác nhau.

### 4.4. uniqueConstraints và indexes

@CollectionTable hỗ trợ khai báo uniqueConstraints và indexes. Ví dụ, nếu cùng một customer không được có hai tag giống nhau, database có thể enforce uniqueness trên cặp customer_id và tag:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id"),
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tag",
        columnNames = {"customer_id", "tag"}
    ),
    indexes = @Index(
        name = "idx_customer_tag_tag",
        columnList = "tag"
    )
)
@Column(name = "tag", nullable = false, length = 80)
private Set<String> tags = new LinkedHashSet<>();
```

Unique constraint giúp bảo vệ dữ liệu ngay ở database, kể cả khi có nhiều instance ứng dụng hoặc một luồng ghi không đi qua collection Java. Index nên được chọn theo truy vấn thực tế, không tạo chỉ vì một cột tồn tại.

Các khai báo này tham gia vào quá trình schema generation của provider. Nếu schema được quản lý bằng Flyway hoặc Liquibase, hãy khai báo constraint và index trong migration để có lịch sử thay đổi rõ ràng. Không giả định annotation tự thay đổi database production khi Hibernate đang dùng ddl-auto=validate hoặc none.

### 4.5. foreignKey

Thuộc tính foreignKey cho phép cấu hình constraint khóa ngoại khi provider sinh schema. Có thể đặt tên constraint hoặc điều khiển việc sinh DDL. Với hệ thống dùng migration, định nghĩa khóa ngoại trong migration thường rõ ràng hơn và có thể review cùng các thay đổi schema khác.

## 5. Collection của basic type

### 5.1. Set<String>

Set phù hợp khi giá trị không cần lặp và không cần lưu thứ tự chèn:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag", nullable = false, length = 80)
private Set<String> tags = new LinkedHashSet<>();
```

LinkedHashSet giữ thứ tự lặp trong bộ nhớ Java, nhưng điều đó không tự động có nghĩa database sẽ lưu và khôi phục thứ tự. Nếu thứ tự là dữ liệu cần bảo toàn, phải cấu hình cơ chế lưu thứ tự riêng.

Set ngăn trùng lặp trong collection đang chạy ở Java. Nếu tính duy nhất là invariant của dữ liệu, thêm unique constraint ở database để bảo vệ trước ghi đồng thời hoặc dữ liệu được ghi từ nguồn khác.

### 5.2. List và thứ tự phần tử

Nếu cần giữ thứ tự phần tử, dùng @OrderColumn:

```java
@ElementCollection
@CollectionTable(
    name = "customer_phone",
    joinColumns = @JoinColumn(name = "customer_id")
)
@OrderColumn(name = "position")
@Column(name = "phone_number", nullable = false)
private List<String> phoneNumbers = new ArrayList<>();
```

Provider lưu vị trí của từng phần tử trong cột position. Khi đọc lại, collection được tái tạo theo thứ tự đã lưu. Việc chèn hoặc xóa ở giữa danh sách có thể khiến nhiều vị trí cần được cập nhật; hãy cân nhắc chi phí nếu danh sách lớn và thay đổi thường xuyên.

Phân biệt:
- @OrderColumn lưu thứ tự vị trí trong database.
- @OrderBy sắp xếp kết quả khi đọc dựa trên thuộc tính hoặc biểu thức sắp xếp được hỗ trợ; nó không lưu thứ tự chèn của collection.

Nếu không cấu hình cơ chế thứ tự, không nên giả định thứ tự hàng trả về từ database là ổn định.

### 5.3. Collection của enum

Enum có thể lưu trong collection table:

```java
public enum UserRole {
    ADMIN,
    EDITOR,
    VIEWER
}
```

```java
@ElementCollection
@CollectionTable(
    name = "user_role",
    joinColumns = @JoinColumn(name = "user_id")
)
@Column(name = "role", nullable = false, length = 30)
@Enumerated(EnumType.STRING)
private Set<UserRole> roles = new HashSet<>();
```

Dùng EnumType.STRING thường dễ đọc và bền hơn ordinal. Nếu lưu ordinal, việc đổi thứ tự khai báo enum có thể khiến dữ liệu cũ bị diễn giải thành giá trị khác. Khi đổi tên enum đã lưu dưới dạng string, cần migration dữ liệu tương ứng.

## 6. Collection của Embeddable type

Khi mỗi phần tử gồm nhiều thuộc tính, có thể tạo value object với @Embeddable:

```java
@Embeddable
public class AddressValue {

    @Column(name = "street_name", nullable = false, length = 150)
    private String street;

    @Column(name = "city_name", nullable = false, length = 100)
    private String city;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    protected AddressValue() {
    }

    public AddressValue(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
```

Entity sở hữu:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_address",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    private List<AddressValue> addresses = new ArrayList<>();

    protected Customer() {
    }

    public void addAddress(AddressValue address) {
        addresses.add(Objects.requireNonNull(address));
    }
}
```

Vì AddressValue là embeddable, nó không có @Id riêng. Các cột street_name, city_name và postal_code được đặt trong customer_address cùng khóa ngoại customer_id.

### 6.1. Dùng AttributeOverride để đổi tên cột

Một embeddable có thể được tái sử dụng ở nhiều vị trí. Nếu muốn tên cột trong collection table khác tên mặc định, dùng @AttributeOverrides:

```java
@ElementCollection
@CollectionTable(
    name = "customer_address",
    joinColumns = @JoinColumn(name = "customer_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "delivery_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "delivery_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "delivery_postal_code")
    )
})
private List<AddressValue> deliveryAddresses = new ArrayList<>();
```

name trong @AttributeOverride là tên thuộc tính Java của embeddable, không phải tên cột database. column.name là tên cột cần dùng trong collection table.

Nếu collection chứa nhiều embeddable có cấu trúc giống nhau, override giúp phân biệt ý nghĩa cột theo ngữ cảnh mà không phải tạo class value object mới chỉ để đổi tên cột.

## 7. Ánh xạ Map

Map hữu ích khi mỗi phần tử có một key xác định, ví dụ các thuộc tính tùy chỉnh của sản phẩm.

```java
@ElementCollection
@CollectionTable(
    name = "product_attribute",
    joinColumns = @JoinColumn(name = "product_id"),
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_attribute_key",
        columnNames = {"product_id", "attribute_key"}
    )
)
@MapKeyColumn(name = "attribute_key", length = 80)
@Column(name = "attribute_value", length = 500)
private Map<String, String> attributes = new HashMap<>();
```

Ở đây:
- product_id liên kết hàng collection với Product.
- attribute_key lưu key của Map.
- attribute_value lưu value của Map.
- Unique constraint bảo đảm một product không có hai hàng cùng key.

Với Map có key là enum, có thể dùng @MapKeyEnumerated. Với key là entity, mapping sẽ có quy tắc khác và cần đánh giá xem mô hình đó còn là element collection hay đã trở thành quan hệ entity.

Khi truy vấn Map trong JPQL, có thể dùng các hàm KEY, VALUE và ENTRY tùy mục đích. Ví dụ:

```java
@Query("""
    select p
    from Product p
    join p.attributes a
    where key(a) = :attributeKey
      and value(a) = :attributeValue
    """)
List<Product> findByAttribute(
    @Param("attributeKey") String attributeKey,
    @Param("attributeValue") String attributeValue
);
```

JPQL tham chiếu thuộc tính Java và tên entity, không tham chiếu trực tiếp tên bảng hoặc tên cột SQL. Nếu cần truy vấn SQL đặc thù database, có thể dùng native query nhưng phải chấp nhận phụ thuộc vào schema cụ thể.

## 8. Schema collection table trông như thế nào?

Với Customer có tập hợp tag, schema minh họa:

```sql
create table customer (
    id bigint generated by default as identity primary key,
    name varchar(150) not null
);

create table customer_tag (
    customer_id bigint not null,
    tag varchar(80) not null,
    constraint fk_customer_tag_customer
        foreign key (customer_id) references customer(id),
    constraint uk_customer_tag
        unique (customer_id, tag)
);
```

Dữ liệu ví dụ:

| customer_id | tag |
|---:|---|
| 10 | vip |
| 10 | newsletter |
| 12 | wholesale |

Customer có id 10 sở hữu hai tag. Customer id 12 sở hữu một tag. Collection table không cần một entity Java riêng để biểu diễn mỗi hàng.

Tên cột, kiểu dữ liệu và constraint trong DDL phải khớp mapping. Kiểu customer_id cần tương thích với khóa chính customer.id. Nếu khóa chính của owner là UUID hoặc composite key, DDL và join columns cũng phải tương ứng.

Đối với collection table, khóa ngoại là rất quan trọng. Nếu không có constraint, có thể xuất hiện hàng mồ côi trỏ tới owner không tồn tại khi có thao tác ghi ngoài JPA. Unique constraint phù hợp cũng giúp bảo vệ invariant của collection.

## 9. Vòng đời, cập nhật và xóa phần tử

Element collection thuộc về entity sở hữu. Ứng dụng thường thay đổi nó thông qua collection trên entity:

```java
customer.addTag("vip");
customer.removeTag("newsletter");
```

Khi owner đang managed trong transaction, Hibernate theo dõi thay đổi collection và đồng bộ chúng khi flush. Cơ chế SQL chính xác phụ thuộc mapping và provider; một số thay đổi có thể dẫn tới delete/insert hàng collection thay vì một câu update đơn giản.

Các điểm cần nhớ:
- Không có repository riêng cho String, enum hoặc embeddable element.
- Không có @Id riêng trên từng phần tử element collection.
- Không dùng orphanRemoval như với @OneToMany; vòng đời phần tử gắn với collection của owner.
- Khi owner bị xóa, provider phải xử lý các hàng collection table theo mapping và constraint. Có thể dùng foreign key và chính sách database phù hợp để bảo vệ toàn vẹn.
- Nếu một phần tử cần được chỉnh sửa độc lập, audit độc lập hoặc tham chiếu từ entity khác, hãy cân nhắc chuyển nó thành entity.

Không nên cập nhật trực tiếp collection table bằng JDBC trong khi persistence context vẫn giữ collection cũ mà không đồng bộ. Nếu có bulk SQL, cần xem xét flush và clear/refresh để tránh state trong bộ nhớ khác với database.

## 10. Fetching, truy vấn và hiệu năng

### 10.1. FetchType.LAZY

Element collection mặc định có fetch type LAZY theo đặc tả. Provider có thể trì hoãn việc tải collection cho tới khi ứng dụng truy cập.

Ví dụ:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_tag",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new HashSet<>();
```

Đọc customer không nhất thiết phải tải tất cả tag. Nhưng nếu truy cập tags sau khi persistence context đóng, Hibernate có thể ném LazyInitializationException.

### 10.2. Truy vấn entity theo phần tử collection

JPQL có thể join collection:

```java
@Query("""
    select distinct c
    from Customer c
    join c.tags tag
    where tag = :tag
    """)
List<Customer> findCustomersWithTag(@Param("tag") String tag);
```

distinct giúp tránh trả về trùng entity khi join tạo nhiều hàng kết quả cho cùng một owner. Với collection lớn, hãy xem xét index trên cột tag hoặc cặp khóa phù hợp với truy vấn.

### 10.3. Tránh N+1

Nếu tải danh sách Customer rồi lần lượt truy cập tags của từng người, provider có thể phát sinh một truy vấn riêng cho mỗi collection. Đây là dạng N+1.

Các cách xử lý:
- Tải collection theo fetch plan rõ ràng bằng EntityGraph hoặc fetch join khi phù hợp.
- Dùng DTO projection cho màn hình chỉ cần một tập dữ liệu cụ thể.
- Dùng batch fetching của Hibernate khi pattern truy cập phù hợp.
- Đo SQL thực tế và số lần round trip thay vì đoán.

Fetch join collection cùng phân trang cần được kiểm tra kỹ vì join có thể nhân số dòng. Có thể phân trang danh sách owner trước rồi tải collection cho nhóm ID đó bằng truy vấn thứ hai.

## 11. Khi nào nên thay ElementCollection bằng Entity?

Element collection phù hợp với value nhỏ, gắn chặt vòng đời owner. Nên chuyển sang entity khi:
- Phần tử cần ID riêng.
- Phần tử có trạng thái hoặc quy trình nghiệp vụ riêng.
- Phần tử được tham chiếu bởi entity khác.
- Cần audit, phân quyền hoặc lịch sử thay đổi riêng cho từng phần tử.
- Cần truy vấn và phân trang phần tử như một tập dữ liệu độc lập.
- Có nhiều quan hệ hoặc metadata phức tạp gắn với phần tử.

Ví dụ OrderLine thường là entity vì dòng hàng có số lượng, đơn giá, chiết khấu, trạng thái và có thể được xử lý riêng. Ngược lại, tập hợp tag của Customer thường là element collection vì mỗi tag chỉ là một value gắn với Customer.

Không nên dùng ElementCollection cho dữ liệu lớn, thay đổi độc lập hoặc cần thao tác hàng loạt phức tạp mà không cân nhắc chi phí collection tracking và SQL do provider sinh ra.

## 12. Kiểm thử mapping @CollectionTable

Một test JPA có thể kiểm tra collection được lưu và nạp lại:

```java
@DataJpaTest
class CustomerCollectionTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private CustomerRepository repository;

    @Test
    void persistsAndLoadsTags() {
        Customer customer = new Customer(Set.of("vip", "newsletter"));
        entityManager.persist(customer);
        entityManager.flush();
        Long id = customer.getId();

        entityManager.clear();

        Customer loaded = repository.findById(id).orElseThrow();

        assertThat(loaded.getTags())
            .containsExactlyInAnyOrder("vip", "newsletter");
    }
}
```

Ví dụ giả định Customer có constructor và getter như phần trước. flush() buộc provider đồng bộ thay đổi xuống database; clear() loại entity managed khỏi persistence context để truy vấn sau không chỉ trả về instance đang có trong bộ nhớ. Test xác nhận dữ liệu có thể được đọc lại từ database.

Nên bổ sung test theo yêu cầu domain:
- Thêm và xóa một phần tử.
- Hai owner có collection độc lập.
- Unique constraint ngăn trùng key/value nếu đó là quy tắc.
- List giữ đúng thứ tự khi dùng @OrderColumn.
- Embeddable được lưu đúng tên cột sau AttributeOverride.
- Map khôi phục đúng key và value.
- Xóa owner xử lý các hàng collection table đúng cách.
- Truy vấn JPQL join collection trả về owner đúng và không trùng.

Với schema production, chạy integration test trên cùng loại database bằng Testcontainers để kiểm tra kiểu dữ liệu, constraint và SQL thực tế.

## 13. Checklist trước khi hoàn thành mapping

- [ ] Phần tử thực sự là basic hoặc embeddable value, không cần entity identity.
- [ ] Collection được đánh dấu @ElementCollection.
- [ ] @CollectionTable có tên bảng và joinColumns rõ ràng.
- [ ] Join column tham chiếu đúng khóa chính owner.
- [ ] Tên cột và kiểu dữ liệu khớp schema/migration.
- [ ] Unique constraint được khai báo nếu domain yêu cầu duy nhất.
- [ ] Index được chọn theo truy vấn thực tế.
- [ ] List có @OrderColumn nếu cần lưu thứ tự.
- [ ] Map có @MapKeyColumn hoặc mapping key phù hợp.
- [ ] Embeddable dùng AttributeOverride khi cần đổi tên cột.
- [ ] Fetch plan phù hợp và collection được truy cập trong transaction.
- [ ] Không dùng JDBC bulk update làm collection managed bị stale.
- [ ] Integration test xác nhận persist, reload, update và delete.
- [ ] Dùng entity riêng nếu phần tử có vòng đời hoặc định danh độc lập.

## 14. Kết luận

@CollectionTable xác định bảng lưu trữ tập hợp basic hoặc embeddable values được khai báo bằng @ElementCollection. joinColumns liên kết các hàng trong bảng này với entity sở hữu; các annotation như @Column, @AttributeOverride, @MapKeyColumn, @OrderColumn, uniqueConstraints và indexes mô tả cấu trúc dữ liệu cụ thể.

Hãy dùng element collection cho value có vòng đời gắn với owner và dùng entity relationship khi phần tử cần định danh, truy vấn hoặc quản lý độc lập. Thiết kế collection table cùng khóa ngoại, uniqueness, thứ tự và index ngay từ đầu sẽ giúp mapping rõ ràng, truy vấn ổn định và schema dễ bảo trì.