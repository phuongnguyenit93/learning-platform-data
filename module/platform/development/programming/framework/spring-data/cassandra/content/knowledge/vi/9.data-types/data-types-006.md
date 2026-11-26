# User-defined type với @UserDefinedType trong Spring Data Cassandra

## 1. User-defined type giải quyết vấn đề gì?

**Apache Cassandra** cung cấp **user-defined type (UDT)** để mô tả một giá trị có cấu trúc gồm nhiều trường được đặt tên, ví dụ địa chỉ giao hàng, tọa độ hoặc thông tin liên hệ. Trong **Spring Data Cassandra**, annotation `@UserDefinedType` ánh xạ kiểu CQL đó thành một lớp Java; entity có thể chứa đối tượng UDT như một thuộc tính và truy cập qua repository, `CassandraTemplate` hoặc truy vấn CQL.

Giả sử ứng dụng quản lý khách hàng cần lưu địa chỉ nhà:

~~~text
Customer
  customer_id: UUID
  display_name: String
  home_address:
    street: String
    city: String
    postal_code: String
~~~

Nếu tách từng thành phần thành những cột `street`, `city`, `postal_code` tại bảng khách hàng, schema vẫn có thể hoạt động. UDT phù hợp khi các trường đó tạo thành **một khái niệm nghiệp vụ có cấu trúc**, được dùng ở nhiều nơi hoặc cần biểu diễn như một giá trị lồng trong hàng. Tuy vậy, UDT **không phải bảng quan hệ độc lập**, không có primary key riêng và không tạo sẵn đường truy vấn hiệu quả theo từng trường.

Sau bài học, bạn cần có thể:

1. Viết CQL `CREATE TYPE` và dùng kiểu mới trong `CREATE TABLE`.
2. Phân biệt **frozen UDT** với **non-frozen UDT** và chọn cách cập nhật phù hợp.
3. Ánh xạ UDT qua `@UserDefinedType`, `@Column` và khi cần `@CassandraType` trong Spring Data Cassandra.
4. Lưu, đọc và cập nhật entity chứa UDT bằng repository hoặc `CassandraTemplate`.
5. Nhận diện các rủi ro khi UDT thay đổi schema, khi có giá trị null, khi đặt UDT trong collection và khi truy vấn/ghi ở quy mô lớn.

Bài thuộc chương **Kiểu dữ liệu** của module `SPRING_DATA_CASSANDRA`. Nó bổ sung kiến thức ánh xạ entity, nhưng việc chọn **partition key**, consistency, paging và kiểm soát hiệu năng vẫn phải dựa trên mô hình dữ liệu phân tán của Cassandra.

## 2. UDT khác bảng Cassandra và kiểu collection ra sao?

| Cách lưu | Ví dụ | Đặc điểm | Tình huống phù hợp |
| --- | --- | --- | --- |
| **Các cột trực tiếp** | `street text, city text` | Schema phẳng, có thể thao tác từng cột | Dữ liệu đơn giản, không cần value object riêng |
| **UDT** | `home_address frozen<postal_address>` | Một giá trị có những trường đặt tên, được lưu trong hàng chứa nó | Nhóm thuộc tính gắn bó với nhau |
| **Collection** | `set<text>`, `map<text,text>` | Tập giá trị đồng nhất hoặc key-value | Danh sách/tag/map có kiểu phần tử ổn định |
| **Bảng riêng** | `addresses_by_customer` | Có khóa chính và partition key riêng; có thể phục vụ đường đọc riêng | Địa chỉ cần được truy vấn, phân trang hoặc quản lý độc lập |

Một UDT được **khai báo trong phạm vi một keyspace** và có thể được tham chiếu từ nhiều bảng trong keyspace đó. Nó mô tả **kiểu dữ liệu của cột**, không tạo ra một partition độc lập. Ví dụ cột `home_address` trong hàng khách hàng vẫn được lưu và truy cập theo primary key của bảng khách hàng.

> **Quy tắc thiết kế:** chọn UDT vì cấu trúc dữ liệu cần biểu diễn; chọn partition key và clustering columns dựa trên những truy vấn cần phục vụ. Không dùng UDT như cách thay thế cho thiết kế bảng theo truy vấn.

## 3. Tạo UDT và bảng bằng CQL

Trong một Cassandra **một node** dành riêng cho thực hành, có thể chuẩn bị keyspace như sau:

~~~sql
-- Chỉ dùng cho môi trường thử nghiệm một node.
CREATE KEYSPACE IF NOT EXISTS app_ks
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE app_ks;

CREATE TYPE IF NOT EXISTS postal_address (
    street text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS customers_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    home_address frozen<postal_address>
);
~~~

Với môi trường nhiều node hoặc production, cần chọn **NetworkTopologyStrategy**, replication factor và tên datacenter phù hợp thực tế, không giữ nguyên `SimpleStrategy`/RF = 1 của ví dụ lab.

Trong schema trên:

- `postal_address` là **tên UDT CQL**, được tạo **trước** bảng tham chiếu nó.
- `street`, `city`, `postal_code` là các **trường của UDT**, không phải tên cột trực tiếp trong `customers_by_id`.
- `home_address` là một **cột** có kiểu `frozen<postal_address>`.
- `customer_id` là **partition/primary key** của bảng; địa chỉ không tham gia định danh hàng.
- Tham chiếu kiểu `postal_address` trong `CREATE TABLE` được phân giải trong `app_ks` vì CQL đã chọn keyspace bằng `USE`.

Để kiểm tra metadata trong `cqlsh`:

~~~sql
DESCRIBE TYPE app_ks.postal_address;
DESCRIBE TABLE app_ks.customers_by_id;
~~~

Khả năng của các lệnh `DESCRIBE` phụ thuộc công cụ CQL client, không phải API Java driver. Trong ứng dụng, hãy dùng cơ chế quản lý schema có phiên bản/di trú phù hợp; annotation Java **không tự bảo đảm** UDT và bảng đã tồn tại trước khi repository sử dụng.

### 3.1. Ghi và đọc giá trị UDT bằng CQL

CQL biểu diễn UDT bằng literal có tên trường:

~~~sql
INSERT INTO app_ks.customers_by_id
    (customer_id, display_name, home_address)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'An',
    {
        street: '12 Nguyen Trai',
        city: 'Ho Chi Minh City',
        postal_code: '700000'
    }
);

SELECT customer_id, display_name, home_address
FROM app_ks.customers_by_id
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Khi ứng dụng nhận dữ liệu từ người dùng, hãy dùng **bind parameter/đối tượng được ánh xạ**, không nối chuỗi từ input vào CQL literal. Những chuỗi như `street` và `city` nằm trong value UDT, còn truy vấn đọc vẫn dựa trên **`customer_id`**.

~~~mermaid
flowchart LR
    A[Java Customer entity] --> B[homeAddress: PostalAddress]
    B --> C[Spring Data converter]
    C --> D[CQL UDT value]
    D --> E[home_address trong customers_by_id]
    E --> F[Partition theo customer_id]
~~~

## 4. Ánh xạ UDT bằng @UserDefinedType

### 4.1. Lớp Java mô tả UDT

Trong Spring Data Cassandra, `@UserDefinedType` xác định lớp ánh xạ tới một kiểu UDT Cassandra. `@Column` giúp đặt chính xác tên trường CQL, đặc biệt khi tên Java dạng camelCase khác tên cột snake_case.

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("postal_address")
public class PostalAddress {

    @Column("street")
    private String street;

    @Column("city")
    private String city;

    @Column("postal_code")
    private String postalCode;

    // Constructor rỗng giúp cách mapping dựa trên property hoạt động đơn giản.
    public PostalAddress() {
    }

    public PostalAddress(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

Điểm cần nhớ:

- `@UserDefinedType("postal_address")` tham chiếu **tên kiểu CQL**, không phải tên bảng.
- `@Column("postal_code")` ánh xạ `postalCode` sang đúng **trường trong UDT**.
- `PostalAddress` **không có `@PrimaryKey`**: đây là value object lồng trong hàng, không phải entity độc lập có khóa.
- Ví dụ dùng POJO có getter/setter cho dễ thấy quá trình mapping. Có thể thiết kế **value object bất biến** bằng constructor binding nếu phiên bản Spring Data Cassandra và cách ánh xạ của dự án hỗ trợ; cần kiểm chứng bằng test tích hợp.
- Không cần ghi `@Table` trên lớp UDT. `@Table` dành cho entity ánh xạ tới bảng.

### 4.2. Entity chứa thuộc tính UDT

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customers_by_id")
public class Customer {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("display_name")
    private String displayName;

    @Column("home_address")
    @CassandraType(
        type = CassandraType.Name.UDT,
        userTypeName = "postal_address"
    )
    private PostalAddress homeAddress;

    public Customer() {
    }

    public Customer(UUID customerId, String displayName,
                    PostalAddress homeAddress) {
        this.customerId = customerId;
        this.displayName = displayName;
        this.homeAddress = homeAddress;
    }

    public UUID getCustomerId() {
        return customerId;
    }

    public void setCustomerId(UUID customerId) {
        this.customerId = customerId;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public PostalAddress getHomeAddress() {
        return homeAddress;
    }

    public void setHomeAddress(PostalAddress homeAddress) {
        this.homeAddress = homeAddress;
    }
}
~~~

Annotation `@CassandraType(type = CassandraType.Name.UDT, userTypeName = "postal_address")` khai báo rõ **kiểu dữ liệu CQL của cột**. Tùy phiên bản Spring Data và metadata converter, một số trường hợp có thể suy ra kiểu UDT từ lớp `@UserDefinedType`; việc khai báo tường minh giúp người học nhận biết mối liên hệ giữa cột và kiểu. **Cú pháp annotation và khả năng tự suy luận cần kiểm thử với đúng phiên bản Spring Boot/Spring Data Cassandra của dự án.**

Entity `Customer` được ánh xạ tới bảng `customers_by_id` trong **keyspace mà session/template đang sử dụng**, trừ khi ứng dụng có cấu hình ánh xạ keyspace tường minh. Đừng nhầm rằng annotation `@UserDefinedType` tự tạo keyspace hoặc có thể tự chọn cluster khác.

### 4.3. Phân biệt ba loại ánh xạ

| Annotation | Áp dụng ở đâu? | Tác dụng chính |
| --- | --- | --- |
| `@Table("customers_by_id")` | Entity `Customer` | Liên hệ class với bảng Cassandra |
| `@UserDefinedType("postal_address")` | Class `PostalAddress` | Liên hệ class với CQL UDT |
| `@Column("postal_code")` | Trường `PostalAddress.postalCode` | Chỉ định đúng tên trường/cột CQL |
| `@CassandraType(...Name.UDT...)` | Thuộc tính `Customer.homeAddress` | Mô tả rõ kiểu dữ liệu của cột UDT khi cần |
| `@PrimaryKey("customer_id")` | Thuộc tính ID của entity | Ánh xạ định danh hàng trong bảng |

UDT value được lưu **bên trong hàng của entity**. Nó không được quản lý thông qua một `CassandraRepository<PostalAddress, ...>` độc lập nếu không có bảng và primary key riêng.

## 5. Lưu và đọc UDT qua Repository, CassandraTemplate

### 5.1. Repository

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerRepository
        extends CassandraRepository<Customer, UUID> {
}
~~~

Với `CustomerRepository` đã được Spring inject, thao tác CRUD thông thường:

~~~java
UUID id = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);

PostalAddress address = new PostalAddress(
    "12 Nguyen Trai", "Ho Chi Minh City", "700000"
);
Customer customer = new Customer(id, "An", address);

repository.save(customer);

Customer loaded = repository.findById(id).orElseThrow();
String city = loaded.getHomeAddress().getCity();
~~~

`save` thao tác trên **hàng Customer**, đồng thời Spring Data chuyển đối tượng `PostalAddress` thành giá trị UDT tương ứng. Không có thao tác “lưu riêng UDT” thành một row trong Cassandra. Nếu `customerId` cố định, thay `homeAddress` là cập nhật dữ liệu của hàng đó, không phải đổi partition key.

### 5.2. CassandraTemplate / CassandraOperations

Trong service đã inject `CassandraOperations`:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CassandraOperations operations;

    public CustomerService(CassandraOperations operations) {
        this.operations = operations;
    }

    public Customer load(UUID id) {
        return operations.selectOneById(id, Customer.class);
    }

    public Customer save(Customer customer) {
        return operations.insert(customer);
    }
}
~~~

Đây là ví dụ **insert một entity mới**; lặp lại `insert` với cùng khóa có thể mang ngữ nghĩa upsert theo CQL/mapping. Trong thực tế cần quyết định rõ lúc nào sử dụng `insert`, `update`, `save` của repository, các điều kiện ghi và TTL để phù hợp yêu cầu nghiệp vụ. `CassandraTemplate` cho phép xây dựng các thao tác/truy vấn linh hoạt hơn, nhưng không thay thế việc thiết kế bảng và khóa đúng.

> **Không thay đổi consistency hoặc ranh giới transaction chỉ nhờ dùng UDT.** Câu CQL vẫn là một thao tác Cassandra với keyspace, partition key, replication factor và consistency level của nó.

## 6. Frozen UDT và non-frozen UDT

### 6.1. Frozen: một giá trị được ghi thay thế theo khối

Trong bảng mẫu, `home_address frozen<postal_address>` biểu diễn địa chỉ như **một giá trị frozen**. Khi muốn đổi thành phố, thông thường ứng dụng cần tạo và ghi **toàn bộ giá trị UDT mới**, bao gồm các trường còn cần giữ.

~~~sql
UPDATE app_ks.customers_by_id
SET home_address = {
    street: '12 Nguyen Trai',
    city: 'Da Nang',
    postal_code: '550000'
}
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Các điểm đáng chú ý:

- `home_address` vẫn nằm trong **cùng hàng**, không tạo thêm partition.
- Ghi một frozen UDT thay thế giá trị cũ của cột; không có cơ chế cập nhật trường bên trong `home_address` trực tiếp như một cell độc lập.
- Nếu writer A và B cùng đọc địa chỉ cũ rồi ghi lại toàn bộ frozen UDT, một bản cập nhật có thể ghi đè dữ liệu trường khác vừa được thay đổi bởi writer còn lại.
- Khi cần kiểm soát cạnh tranh, thiết kế phiên bản nghiệp vụ, xử lý ghi có điều kiện phù hợp với quy tắc Cassandra và xem xét chi phí LWT nếu thực sự cần.

**Ví dụ không hợp lệ khi cột frozen**:

~~~sql
-- Minh họa thao tác không được phép với frozen UDT:
UPDATE app_ks.customers_by_id
SET home_address.city = 'Da Nang'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

### 6.2. Non-frozen: có thể cập nhật từng trường theo khả năng phiên bản

Khi schema khai báo trực tiếp một UDT **không frozen**, những phiên bản Cassandra hỗ trợ kiểu lưu này cho phép cập nhật trường UDT độc lập:

~~~sql
CREATE TABLE app_ks.customers_address_mutable_by_id (
    customer_id uuid PRIMARY KEY,
    home_address postal_address
);

UPDATE app_ks.customers_address_mutable_by_id
SET home_address.city = 'Da Nang'
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
~~~

Khả năng dùng non-frozen UDT phụ thuộc **phiên bản Cassandra, vị trí dùng kiểu và hạn chế của schema**. Khi triển khai, hãy xác minh DDL/CQL trên chính môi trường mục tiêu và kiểm tra converter Spring Data Cassandra có phát ra thao tác cập nhật từng trường hay không. **Gọi `repository.save(entity)` không đồng nghĩa Spring Data tự phát lệnh `SET home_address.city = ...`**; thường cần viết thao tác cập nhật CQL tường minh nếu muốn kiểm soát từng trường.

| Tiêu chí | Frozen UDT | Non-frozen UDT |
| --- | --- | --- |
| Cách nhìn giá trị | Một giá trị tổng hợp | Có thể quản lý các trường như những phần có thể cập nhật độc lập |
| Ghi thay địa chỉ | Ghi toàn bộ UDT | Có thể ghi toàn bộ hoặc cập nhật trường theo hỗ trợ |
| `SET home_address.city = ...` | **Không** | **Có thể**, nếu schema và phiên bản cho phép |
| Nguy cơ lost update khi thay toàn bộ địa chỉ | Có nếu các writer dùng snapshot cũ | Vẫn có nếu thao tác ghi không được phối hợp |
| Tính phù hợp | Value object thay đổi cùng lúc, cần đơn giản hóa ngữ nghĩa | Khi nghiệp vụ thường xuyên cập nhật trường riêng lẻ |

### 6.3. UDT trong collection và UDT lồng nhau

Ví dụ lưu nhiều địa chỉ cho một khách hàng:

~~~sql
CREATE TABLE app_ks.customer_address_lists_by_id (
    customer_id uuid PRIMARY KEY,
    addresses list<frozen<postal_address>>
);
~~~

Trong collections, việc dùng `frozen<postal_address>` làm **kiểu phần tử** thường là cấu trúc cần thiết để Cassandra xử lý mỗi phần tử UDT như một giá trị. Tương tự, có thể gặp `map<text, frozen<postal_address>>` tùy access pattern và phiên bản Cassandra.

Nhưng collection lớn không nên được xem là bảng con vô hạn: đọc/ghi một danh sách địa chỉ rất lớn có thể tăng kích thước hàng, chi phí phân trang và tombstone. Nếu mỗi địa chỉ có ID, vòng đời, tần suất cập nhật và yêu cầu truy vấn riêng, cân nhắc thiết kế **bảng `addresses_by_customer`** với primary key phù hợp.

Khi ánh xạ `List<PostalAddress>` hoặc `Map<String, PostalAddress>`, metadata kiểu phần tử và custom conversion có thể cần khai báo `@CassandraType` với thông tin UDT đúng theo **phiên bản Spring Data**. Đừng giả định một annotation áp dụng cho cột UDT đơn lẻ có thể được sao chép nguyên cho mọi collection lồng nhau.

## 7. Những giới hạn quan trọng của UDT

### 7.1. UDT không tạo khả năng truy vấn tùy ý

Không thể suy ra rằng vì UDT có trường `city`, Cassandra sẽ tự tìm nhanh “mọi khách hàng ở Da Nang”. Bảng `customers_by_id` chỉ được thiết kế với **primary key `customer_id`**. Truy vấn theo thành phố cần đường truy cập riêng, một bảng được thiết kế theo truy vấn hoặc cơ chế lập chỉ mục/search được lựa chọn có cơ sở và kiểm chứng chi phí.

Ví dụ một bảng phục vụ truy vấn liệt kê khách hàng theo thành phố trong từng tenant:

~~~sql
CREATE TABLE app_ks.customers_by_tenant_city (
    tenant_id uuid,
    city text,
    customer_id uuid,
    display_name text,
    PRIMARY KEY ((tenant_id, city), customer_id)
);
~~~

Đây chỉ là **thiết kế minh họa**: cần đánh giá cardinality và kích thước partition, nhất là thành phố có nhiều khách hàng, đồng thời tổ chức đồng bộ giữa bảng theo ID và bảng theo thành phố khi địa chỉ đổi. UDT giúp biểu diễn địa chỉ, còn cách tìm theo thành phố là quyết định **query-first modeling**.

### 7.2. Thay đổi schema UDT cần migration

Giả sử nghiệp vụ bổ sung quốc gia:

~~~sql
ALTER TYPE app_ks.postal_address
ADD country text;
~~~

Trước khi chạy trên hệ thống thật:

1. Kiểm tra phiên bản Cassandra và khả năng thay đổi type đang được dùng bởi các bảng/collection.
2. Chuẩn bị migration và thử trên dữ liệu cũ; giá trị UDT ghi trước khi có trường mới có thể không có giá trị `country`.
3. Thêm trường Java tương ứng, ví dụ `@Column("country")`, và cập nhật API/service.
4. Kiểm tra driver/schema metadata và cơ chế làm mới metadata ở từng phiên bản; ứng dụng cũ/new chạy đồng thời cần được thử với cả giá trị có hoặc thiếu trường.
5. Kiểm thử rolling deploy và rollback. Thay đổi kiểu của trường, xóa hoặc đổi tên trường có thể bị hạn chế hoặc làm hỏng tương thích, tùy phiên bản.

Không chọn tên UDT chỉ dựa trên tên lớp Java rồi để mỗi lần khởi động ứng dụng tự chỉnh schema production. **Schema UDT là hợp đồng giữa database và nhiều phiên bản ứng dụng**, nên cần quản lý thay đổi một cách có chủ đích.

### 7.3. Null, unset và giá trị thiếu trường

Một địa chỉ có thể không có mã bưu chính. Trong Java, `postalCode` là `null`; trong dữ liệu Cassandra, phải phân biệt:

- **Trường UDT không được cung cấp/được đọc là null:** không có giá trị cụ thể cho trường.
- **Ghi `null` trong mutation CQL:** có thể biểu diễn việc xóa giá trị, tạo tombstone theo ngữ nghĩa Cassandra.
- **`UNSET` khi bind statement:** thường mang nghĩa **không thay đổi giá trị hiện có** ở những ngữ cảnh hỗ trợ, khác với ghi null.
- **Frozen UDT ghi lại toàn bộ:** trường bị bỏ sót trong giá trị mới không tự lấy lại giá trị trước đó; cần giữ rõ những trường cần bảo toàn.

Không áp dụng quy tắc “null thì bỏ qua” một cách mơ hồ cho mọi lệnh `save`/`update`. Hành vi phụ thuộc loại mutation, cấu hình mapper và cách bind tham số. Khi bài toán có cập nhật một phần, hãy viết test cho việc giữ nguyên, xóa và thay đổi giá trị; nếu cần thao tác từng trường thường xuyên, đánh giá thiết kế non-frozen hoặc các cột riêng.

### 7.4. TTL, tombstone và hiệu năng

UDT nằm trong một cột/hàng Cassandra nên không tự có vòng đời tách biệt khỏi chiến lược lưu dữ liệu:

- Ghi với **TTL** làm giá trị có thể hết hạn; với frozen UDT, việc thay cả cột là thao tác trên một giá trị tổng hợp.
- Xóa hoặc ghi null có thể sinh **tombstone**; việc thay thế thường xuyên và dữ liệu hết hạn cần được xem xét trong bối cảnh compaction/đọc.
- UDT có nhiều trường và dữ liệu lớn làm tăng kích thước row, chi phí truyền và deserialize, đặc biệt khi truy vấn phải đọc nhiều hàng.
- Không biến UDT thành một cấu trúc lồng sâu/collection ngày càng lớn chỉ vì dễ ánh xạ với Java class.

Nếu hệ thống có lưu lượng lớn, hãy đo latency, kích thước partition, mức đọc/ghi, TTL và số tombstone theo **truy vấn thực tế**. Annotation `@UserDefinedType` chỉ mô tả mapping; nó không tự tối ưu hiệu năng Cassandra.

## 8. UDT ở hai tầng: Spring mapping và Java driver

Spring Data Cassandra có thể ánh xạ `PostalAddress` sang CQL UDT thông qua converter và metadata. Ở tầng Java driver, một UDT được biểu diễn qua metadata kiểu và **`UdtValue`**; đây là kiểu dữ liệu của driver, **khác** với annotation `@UserDefinedType`.

Ví dụ cơ chế tạo giá trị UDT khi dùng Java driver trực tiếp (dạng minh họa, yêu cầu session đã kết nối và schema đã tồn tại):

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

CqlIdentifier keyspace = CqlIdentifier.fromCql("app_ks");
CqlIdentifier typeName = CqlIdentifier.fromCql("postal_address");

UserDefinedType addressType = session.getMetadata()
    .getKeyspace(keyspace)
    .flatMap(ks -> ks.getUserDefinedType(typeName))
    .orElseThrow();

UdtValue addressValue = addressType.newValue()
    .setString("street", "12 Nguyen Trai")
    .setString("city", "Ho Chi Minh City")
    .setString("postal_code", "700000");
~~~

`session` là `CqlSession` đã được cấu hình đúng cluster/keyspace, và đoạn này chỉ minh họa lớp **driver API**. Khi dùng repository/`CassandraTemplate`, thường để Spring Data tự chuyển đổi `PostalAddress`; không cần tự tạo `UdtValue` mỗi lần. Khi định nghĩa custom converter hoặc truy vấn driver ở mức thấp, cần phân biệt:

| Tầng | Kiểu hoặc annotation | Mục đích |
| --- | --- | --- |
| Cassandra schema | `CREATE TYPE postal_address` | Định nghĩa cấu trúc lưu trữ ở keyspace |
| Spring Data mapping | `@UserDefinedType("postal_address")` | Ánh xạ Java class với CQL UDT |
| Spring Data property typing | `@CassandraType(type = Name.UDT, ...)` | Khai báo kiểu Cassandra của một field khi cần |
| Java driver | `UserDefinedType` và `UdtValue` | Truy cập metadata và giá trị UDT ở cấp driver |

Tên `UserDefinedType` xuất hiện trong **hai package khác nhau**. Đừng import nhầm `com.datastax.oss.driver.api.core.type.UserDefinedType` khi muốn đặt annotation trên lớp Java: annotation Spring thuộc `org.springframework.data.cassandra.core.mapping.UserDefinedType`.

## 9. Keyspace, phiên bản và consistency khi dùng UDT

### 9.1. UDT được định nghĩa theo keyspace

UDT `app_ks.postal_address` thuộc `app_ks`. Một keyspace khác có thể định nghĩa UDT cùng tên nhưng khác trường; **cùng tên không đảm bảo cùng cấu trúc**. Nếu ứng dụng có nhiều session/template cho nhiều keyspace, cần kiểm tra schema UDT của **từng keyspace** và mapping/repository được gắn đúng session.

Đối với dữ liệu phân tán, các node có thể cần thời gian nhận schema mới. Triển khai type/table sau migration cần đợi schema agreement theo quy trình phù hợp, kiểm tra trạng thái driver metadata và tránh đưa code phụ thuộc trường mới vào phục vụ trước khi schema đã sẵn sàng trong các node liên quan.

### 9.2. UDT không sửa được bài toán consistency

Một thao tác ghi `home_address` vẫn phải đi qua coordinator tới replica của partition `customer_id`. Thành công/thất bại phụ thuộc replication, consistency level và tình trạng cluster. `WriteTimeout` không khẳng định mutation chưa xảy ra; khi retry, cần thiết kế idempotency và tránh làm mất các cập nhật đồng thời.

Ghi một frozen UDT có thể là một mutation tới cột của hàng, nhưng điều đó **không tạo giao dịch ACID bao trùm nhiều partition hay bảng khác**. Nếu thay địa chỉ đồng thời phải cập nhật bảng `customers_by_tenant_city`, hai bảng có thể tạm thời không đồng bộ; cần thiết kế cơ chế đồng bộ, đối soát và xử lý lỗi từng phần.

### 9.3. Paging không dựa vào cấu trúc UDT

UDT là **giá trị của một cột**. Paging trong Cassandra đọc các hàng theo truy vấn/partition key và paging state của driver. Việc thêm UDT vào entity không mang lại phân trang cho các trường nội bộ của UDT; nếu địa chỉ cần được phân trang độc lập, cần xem lại mô hình bảng.

## 10. Kiểm thử mapping UDT có ý nghĩa

Unit test lớp `PostalAddress` có thể kiểm tra constructor, getter/setter và validation, nhưng **không đủ** để phát hiện tên trường CQL sai, UDT chưa tạo hoặc converter không đọc được nested value. Nên có **test tích hợp với Cassandra thử nghiệm**.

### 10.1. Chuẩn bị fixture

Tạo keyspace/type/table như phần 3. Với Spring Boot dùng các phiên bản có nhóm property `spring.cassandra`, ví dụ:

~~~yaml
spring:
  cassandra:
    contact-points:
      - 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: app_ks
~~~

**`datacenter1` chỉ là giá trị minh họa**; phải lấy tên datacenter thực tế của cluster và chọn phiên bản Spring Boot/Spring Data/Java driver tương thích. Một số dòng Spring Boot cũ dùng `spring.data.cassandra.*` thay vì `spring.cassandra.*`.

### 10.2. Các tình huống nên kiểm tra

| Kiểm tra | Hành động | Kết quả kỳ vọng |
| --- | --- | --- |
| Schema đúng | Đọc metadata `postal_address` | Có đủ `street`, `city`, `postal_code` trong keyspace đúng |
| Ghi/đọc UDT | Lưu `Customer` qua repository, tìm bằng `customer_id` | Các trường của `PostalAddress` được đọc đúng |
| Cập nhật frozen | Thay cả `homeAddress` rồi lưu | Giá trị mới thay thế, không cần đổi `customer_id` |
| Giá trị thiếu | Ghi dữ liệu với `postalCode = null` theo chiến lược rõ ràng | Quan sát đúng ngữ nghĩa null/tombstone và đọc lại |
| Non-frozen | Thử cập nhật `home_address.city` trên bảng non-frozen | Hoạt động nếu schema/phiên bản hỗ trợ; frozen từ chối |
| Tương thích schema | Thêm trường `country` trên môi trường thử nghiệm | App cũ/mới có hành vi rõ ràng khi gặp giá trị thiếu trường |
| Tên keyspace | Dùng hai keyspace có UDT trùng tên | Repository chỉ dùng schema của keyspace được định cấu hình |
| Query-first | Thử yêu cầu tìm theo `city` | Không lạm dụng truy vấn quét; có kế hoạch bảng/đường đọc phù hợp |

Ví dụ test kiểm tra round-trip mapping, giả định Spring context đã inject repository và dữ liệu thử nghiệm được cô lập:

~~~java
@Test
void shouldRoundTripUserDefinedAddress() {
    UUID id = UUID.randomUUID();
    Customer saved = new Customer(
        id,
        "An",
        new PostalAddress("12 Nguyen Trai", "Ho Chi Minh City", "700000")
    );

    repository.save(saved);
    Customer loaded = repository.findById(id).orElseThrow();

    assertEquals("An", loaded.getDisplayName());
    assertNotNull(loaded.getHomeAddress());
    assertEquals("12 Nguyen Trai", loaded.getHomeAddress().getStreet());
    assertEquals("Ho Chi Minh City", loaded.getHomeAddress().getCity());
    assertEquals("700000", loaded.getHomeAddress().getPostalCode());
}
~~~

Đoạn trích cần JUnit 5 imports, `repository` được inject, Cassandra/schema thử nghiệm và dọn dữ liệu theo môi trường test. Nó kiểm tra được **mapping Java ↔ Cassandra**, nhưng chưa thay thế test cho consistency, hiệu năng và nhiều writer cùng cập nhật frozen UDT.

## 11. Sai lầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`@UserDefinedType` tạo ra một bảng mới.” | Annotation ánh xạ **kiểu dữ liệu**, không tạo entity/table độc lập |
| “UDT có thể dùng repository riêng như một entity có ID.” | Muốn repository riêng cần bảng và primary key thật |
| “Frozen UDT cập nhật từng trường tùy ý.” | Với frozen, phải thay **toàn bộ giá trị UDT** |
| “Bất kỳ non-frozen UDT nào cũng chạy giống nhau ở mọi phiên bản.” | Cần kiểm tra hỗ trợ của Cassandra và mapper |
| “Thêm UDT là có thể `WHERE city = ?` hiệu quả.” | Truy vấn phải được thiết kế theo partition key/index thích hợp |
| “Hai keyspace có UDT cùng tên thì chắc chắn cùng schema.” | UDT có phạm vi **keyspace**, metadata có thể khác nhau |
| “Ghi null luôn giống UNSET.” | Ghi null có thể xóa giá trị; unset có thể giữ nguyên trong thao tác hỗ trợ |
| “`@CassandraType` thay thế hoàn toàn `@UserDefinedType`.” | Chúng mô tả những phần khác nhau của mapping và có thể phối hợp |
| “Lưu UDT bảo đảm transaction nhiều bảng.” | UDT là giá trị cột; giới hạn consistency/transaction Cassandra vẫn giữ nguyên |
| “Thêm nhiều trường UDT không ảnh hưởng tài nguyên.” | Giá trị lớn làm tăng kích thước hàng, truyền tải và chi phí deserialize |

## 12. Thực hành tổng hợp và câu hỏi tự kiểm tra

**Bài tập:** xây dựng API tìm và cập nhật địa chỉ khách hàng theo `customer_id`. Dùng bảng `customers_by_id` và UDT `postal_address` như ví dụ. Khi người dùng chuyển thành phố, hệ thống phải cập nhật địa chỉ và kiểm tra lại giá trị đã lưu.

Các bước đề xuất:

1. Tạo keyspace lab, `CREATE TYPE`, `CREATE TABLE` và kiểm tra schema qua CQL.
2. Tạo `PostalAddress` với `@UserDefinedType` và `Customer` với field UDT; đối chiếu tên cột Java/CQL.
3. Tạo `CustomerRepository` hoặc dùng `CassandraTemplate`; ghi một khách hàng, đọc lại từng trường.
4. Thay địa chỉ trên bảng **frozen** bằng cả đối tượng; xác minh `customer_id` không đổi.
5. Tạo bảng thử **non-frozen**, thử sửa riêng `city` bằng CQL và so sánh với frozen.
6. Thử địa chỉ thiếu `postal_code` và một migration thêm `country`, ghi lại các trường hợp cần xử lý.
7. Giả lập hai writer đọc địa chỉ cũ rồi cập nhật khác trường; mô tả nguy cơ ghi đè và một chiến lược hạn chế.
8. Nếu nghiệp vụ yêu cầu “liệt kê khách hàng theo thành phố”, thiết kế **bảng theo truy vấn** và cách đồng bộ khi thay đổi thành phố, thay vì kỳ vọng UDT tự tạo chỉ mục.

Tự trả lời:

1. UDT khác table và `map<text,text>` ở điểm nào?
2. `@UserDefinedType` được đặt trên lớp nào? `@Table` được đặt trên lớp nào?
3. Vì sao `postal_code` cần khai báo mapping rõ nếu field Java là `postalCode`?
4. Câu lệnh `CREATE TYPE` và `CREATE TABLE` phải triển khai theo thứ tự nào?
5. Giá trị `frozen<postal_address>` được cập nhật khác gì một cột UDT non-frozen?
6. Khi nào nên dùng `list<frozen<postal_address>>` và khi nào nên tạo bảng địa chỉ riêng?
7. UDT có tự giúp truy vấn tất cả khách hàng theo `city` không? Vì sao?
8. Sau khi `ALTER TYPE ADD country`, ứng dụng và dữ liệu cũ cần lưu ý điều gì?
9. Sự khác nhau giữa Spring annotation `@UserDefinedType` và driver class `UserDefinedType` là gì?
10. Tại sao đổi repository sang `CassandraTemplate` không tự giải quyết lost update, timeout hay paging?

**Ghi nhớ:** **`@UserDefinedType` biến một CQL user-defined type thành một value object Java có cấu trúc**. Giá trị đó vẫn thuộc một hàng Cassandra, nằm dưới primary key và consistency level của bảng chứa nó. Dùng UDT khi nhóm trường thực sự là một khái niệm nghiệp vụ, lựa chọn frozen/non-frozen có chủ đích, quản lý schema theo phiên bản và luôn kiểm tra mapping trên Cassandra thực tế.
