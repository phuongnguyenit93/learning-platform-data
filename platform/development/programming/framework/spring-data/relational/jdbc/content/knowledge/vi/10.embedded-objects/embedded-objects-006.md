# Xử lý null toàn bộ, null một phần và đối tượng nhúng lồng nhau

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, một value object có thể được nhúng vào entity bằng `@Embedded`. Các thuộc tính của value object được trải phẳng thành các cột của cùng bảng với entity chứa nó. Vì vậy, khi đọc dữ liệu, framework phải quyết định lúc nào một nhóm cột biểu diễn **đối tượng nhúng không tồn tại**, lúc nào biểu diễn **đối tượng có một vài thuộc tính null**, và lúc nào cần dựng một đối tượng nhúng rỗng.

Quyết định này được điều khiển bởi `onEmpty` của `@Embedded`:

- `Embedded.OnEmpty.USE_NULL`: nếu **tất cả cột thuộc đối tượng nhúng đều SQL NULL**, giá trị thuộc tính được dựng thành `null`.
- `Embedded.OnEmpty.USE_EMPTY`: nếu tất cả cột đều SQL NULL, framework vẫn dựng một instance của kiểu nhúng; các thuộc tính bên trong nhận giá trị null/default tương ứng.

Với đối tượng nhúng lồng nhau, mỗi cấp có thể có prefix và chính sách `onEmpty` riêng. Hiểu rõ phạm vi cột của từng cấp giúp tránh nhầm lẫn giữa “địa chỉ không tồn tại”, “địa chỉ có nhưng thiếu thành phố” và “địa chỉ có nhưng chưa có tọa độ”.

## 1. Đối tượng nhúng được lưu như thế nào?

Giả sử một hồ sơ khách hàng có địa chỉ giao hàng. Địa chỉ gồm đường, thành phố và một đối tượng tọa độ tùy chọn. Tọa độ lại gồm vĩ độ và kinh độ.

Mô hình Java:

~~~text
CustomerProfile
  id
  displayName
  shippingAddress: Address
      street
      city
      geoPoint: GeoPoint
          latitude
          longitude
~~~

Với Spring Data JDBC, các thuộc tính được trải phẳng vào bảng:

~~~text
customer_profiles
  id
  display_name
  shipping_street
  shipping_city
  shipping_geo_latitude
  shipping_geo_longitude
~~~

~~~mermaid
flowchart TB
    Profile["CustomerProfile<br/>Entity / Aggregate Root"]
    Address["Address<br/>Value Object"]
    Geo["GeoPoint<br/>Value Object lồng nhau"]
    Profile -->|"@Embedded<br/>prefix = shipping_"| Address
    Address -->|"@Embedded<br/>prefix = geo_"| Geo
    Profile --> Table[("customer_profiles")]
    Address --> Table
    Geo --> Table
    Table --- C1["shipping_street"]
    Table --- C2["shipping_city"]
    Table --- C3["shipping_geo_latitude"]
    Table --- C4["shipping_geo_longitude"]
~~~

Hai cấp value object **không tạo ra hai bảng riêng**. Chúng là các giá trị thuộc về hồ sơ, được lưu thành các cột trong bảng `customer_profiles`. `@Embedded` không phải quan hệ `@OneToOne` và không cần khóa ngoại để nối sang một bảng địa chỉ.

## 2. Quy tắc USE_NULL và USE_EMPTY

`onEmpty` chỉ xét trạng thái **toàn bộ các cột thuộc phạm vi của embedded object**. Hai lựa chọn có ý nghĩa khác nhau:

| Cấu hình | Tất cả cột của object là SQL NULL | Kết quả khi đọc |
|---|---|---|
| `USE_NULL` | Có | Thuộc tính embedded là Java `null` |
| `USE_EMPTY` | Có | Framework tạo instance; các trường bên trong được ánh xạ từ các giá trị null/default |
| Cả hai | Có ít nhất một cột không NULL | Framework tạo instance và ánh xạ từng thuộc tính |

Ví dụ:

~~~java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Address shippingAddress;
~~~

Nếu cả `shipping_street`, `shipping_city`, `shipping_geo_latitude` và `shipping_geo_longitude` đều là SQL `NULL`, `shippingAddress` được đọc thành Java `null`.

Nếu `shipping_street = '12 Nguyễn Trãi'` nhưng các cột còn lại là `NULL`, `shippingAddress` vẫn là một object `Address`; chỉ các thuộc tính chưa có dữ liệu mang giá trị null. Framework không xóa cả object chỉ vì một vài cột con null.

Nếu dùng `USE_EMPTY`:

~~~java
@Embedded(
    prefix = "billing_",
    onEmpty = Embedded.OnEmpty.USE_EMPTY
)
private Address billingAddress;
~~~

Khi toàn bộ cột `billing_*` là SQL `NULL`, `billingAddress` vẫn được dựng thành instance `Address` với các trường tương ứng null/default.

**Điểm mấu chốt:** `USE_NULL` phân biệt “không có giá trị embedded” bằng trạng thái toàn-null; `USE_EMPTY` chủ động biến trạng thái toàn-null đó thành một object rỗng. Khi có ít nhất một cột khác null, cả hai chính sách đều cần dựng object để giữ giá trị đã lưu.

## 3. Ví dụ Java với hai cấp embedded

Ta dùng ba kiểu:

- `CustomerProfile` là entity được lưu vào bảng.
- `Address` là value object được nhúng trong profile.
- `GeoPoint` là value object được nhúng trong Address.

### GeoPoint.java

~~~java
package com.example.profile;

public class GeoPoint {

    private Double latitude;
    private Double longitude;

    protected GeoPoint() {
        // Dành cho Spring Data JDBC.
    }

    public GeoPoint(Double latitude, Double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public Double getLatitude() {
        return latitude;
    }

    public Double getLongitude() {
        return longitude;
    }
}
~~~

Ta dùng `Double` thay vì `double` vì tọa độ có thể thiếu. Nếu dùng primitive `double`, Java không thể biểu diễn null và giá trị mặc định thường là `0.0`; điều này làm mất khác biệt giữa “chưa có tọa độ” và tọa độ thực sự bằng 0.

### Address.java

~~~java
package com.example.profile;

import org.springframework.data.relational.core.mapping.Embedded;

public class Address {

    private String street;
    private String city;

    @Embedded(
        prefix = "geo_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private GeoPoint geoPoint;

    protected Address() {
        // Dành cho Spring Data JDBC.
    }

    public Address(String street, String city, GeoPoint geoPoint) {
        this.street = street;
        this.city = city;
        this.geoPoint = geoPoint;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public GeoPoint getGeoPoint() {
        return geoPoint;
    }
}
~~~

Ở cấp Address, các cột của tọa độ có prefix `geo_`. Khi Address được nhúng vào Profile với prefix `shipping_`, tên cột cuối cùng được ghép thành `shipping_geo_latitude` và `shipping_geo_longitude`.

### CustomerProfile.java

~~~java
package com.example.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profiles")
public class CustomerProfile {

    @Id
    private Long id;

    private String displayName;

    @Embedded(
        prefix = "shipping_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private Address shippingAddress;

    @Embedded(
        prefix = "billing_",
        onEmpty = Embedded.OnEmpty.USE_EMPTY
    )
    private Address billingAddress;

    protected CustomerProfile() {
        // Dành cho Spring Data JDBC.
    }

    public CustomerProfile(
            String displayName,
            Address shippingAddress,
            Address billingAddress) {
        this.displayName = displayName;
        this.shippingAddress = shippingAddress;
        this.billingAddress = billingAddress;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }
}
~~~

Trong ví dụ:

- `shippingAddress` dùng `USE_NULL`: tất cả cột `shipping_*` null thì object là null.
- `billingAddress` dùng `USE_EMPTY`: tất cả cột `billing_*` null thì vẫn có instance Address rỗng.
- Bên trong `Address`, `geoPoint` dùng `USE_NULL`: nếu Address tồn tại nhưng cả hai cột tọa độ null, `geoPoint` là null.

Chính sách được cấu hình theo **từng thuộc tính embedded**, không phải một cài đặt toàn cục áp dụng cho mọi value object trong ứng dụng.

## 4. Prefix lồng nhau và tên cột cuối cùng

Prefix của cấp ngoài và cấp trong được ghép nối. Với các annotation trên:

| Thuộc tính Java | Prefix ngoài | Prefix trong | Cột SQL |
|---|---|---|---|
| `shippingAddress.street` | `shipping_` | — | `shipping_street` |
| `shippingAddress.city` | `shipping_` | — | `shipping_city` |
| `shippingAddress.geoPoint.latitude` | `shipping_` | `geo_` | `shipping_geo_latitude` |
| `shippingAddress.geoPoint.longitude` | `shipping_` | `geo_` | `shipping_geo_longitude` |
| `billingAddress.street` | `billing_` | — | `billing_street` |
| `billingAddress.geoPoint.latitude` | `billing_` | `geo_` | `billing_geo_latitude` |

Khi nhúng cùng một kiểu `Address` nhiều lần vào entity, prefix khác nhau giúp tránh xung đột tên cột. Nếu không đặt prefix, các trường như `street` hoặc `city` có thể đụng nhau hoặc không tạo được mapping như mong muốn.

Prefix cũng giúp người đọc schema nhận ra nhóm cột nào thuộc value object nào. Hãy chọn tên prefix nhất quán với domain, thường kết thúc bằng dấu gạch dưới để tên cột dễ đọc.

## 5. Schema SQL cho đối tượng nhúng

Vì cả địa chỉ giao và địa chỉ thanh toán có thể vắng mặt hoặc thiếu một phần, các cột của embedded object cần cho phép null trong schema minh họa:

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,

    shipping_street VARCHAR(160),
    shipping_city VARCHAR(100),
    shipping_geo_latitude DOUBLE PRECISION,
    shipping_geo_longitude DOUBLE PRECISION,

    billing_street VARCHAR(160),
    billing_city VARCHAR(100),
    billing_geo_latitude DOUBLE PRECISION,
    billing_geo_longitude DOUBLE PRECISION
);
~~~

Đây là cú pháp PostgreSQL. Với MySQL, thay cột ID bằng `BIGINT AUTO_INCREMENT` và dùng kiểu số phù hợp như `DOUBLE` cho tọa độ. Các cột địa chỉ vẫn cần cho phép `NULL` để biểu diễn object vắng mặt hoặc object có một số trường chưa có dữ liệu.

Không có bảng `addresses` riêng trong mô hình này. Nếu địa chỉ cần được chia sẻ, quản lý vòng đời độc lập hoặc có nhiều quan hệ tham chiếu, hãy xem xét entity/aggregate riêng và lưu ID tham chiếu thay vì embedded value object.

## 6. Bốn trạng thái dữ liệu thường gặp

Giả sử `shippingAddress` dùng `USE_NULL` và `Address.geoPoint` dùng `USE_NULL`.

| Trạng thái | shipping_street | shipping_city | geo_latitude | geo_longitude | Kết quả khi đọc |
|---|---|---|---|---|---|
| Không có địa chỉ | NULL | NULL | NULL | NULL | `shippingAddress == null` |
| Có địa chỉ, thiếu thành phố và tọa độ | Có giá trị | NULL | NULL | NULL | Address có; city null; geoPoint null |
| Có địa chỉ và một phần tọa độ | Có giá trị | Có giá trị | Có giá trị | NULL | Address có; GeoPoint có với longitude null |
| Có địa chỉ đầy đủ | Có giá trị | Có giá trị | Có giá trị | Có giá trị | Address và GeoPoint đều có đầy đủ trường |

Ví dụ các hàng dữ liệu:

~~~sql
INSERT INTO customer_profiles (
    display_name,
    shipping_street,
    shipping_city,
    shipping_geo_latitude,
    shipping_geo_longitude
) VALUES
    ('An', NULL, NULL, NULL, NULL),
    ('Bình', '12 Nguyễn Trãi', NULL, NULL, NULL),
    ('Chi', '25 Lê Lợi', 'Đà Nẵng', 16.0678, NULL),
    ('Dũng', '1 Đồng Khởi', 'TP. Hồ Chí Minh', 10.7769, 106.7009);
~~~

Kết quả mapping:

- Hồ sơ `An`: tất cả cột shipping null, vì vậy `shippingAddress` là null.
- Hồ sơ `Bình`: có street, nên `shippingAddress` là object; city null; cả hai cột geo null nên `geoPoint` là null.
- Hồ sơ `Chi`: Address có; latitude có giá trị nên GeoPoint được dựng; longitude vẫn null.
- Hồ sơ `Dũng`: Address và GeoPoint đều có đủ giá trị.

### NULL toàn bộ khác NULL một phần

Đối với `USE_NULL`, framework không kiểm tra “mọi thuộc tính có đầy đủ hay không”. Nó chỉ cần biết **có ít nhất một cột trong phạm vi embedded object khác SQL NULL hay không**:

~~~text
Tất cả cột = NULL
    -> embedded object = null

Có ít nhất một cột != NULL
    -> tạo embedded object
       -> từng thuộc tính được ánh xạ riêng
       -> thuộc tính nào SQL NULL thì có giá trị null/default tương ứng
~~~

Do đó, `street` có giá trị trong khi `city` null là một Address hợp lệ về mặt mapping. Việc địa chỉ đó có hợp lệ theo nghiệp vụ hay không là trách nhiệm validation/domain và có thể được bổ sung bằng CHECK constraint.

## 7. Cách xử lý object rỗng với USE_EMPTY

Đổi chính sách của `shippingAddress` thành:

~~~java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_EMPTY
)
private Address shippingAddress;
~~~

Khi toàn bộ cột `shipping_*` là SQL NULL, Spring Data JDBC vẫn dựng một instance Address. Kết quả có dạng:

~~~java
Address address = profile.getShippingAddress();

// address khác null
// address.getStreet() == null
// address.getCity() == null
// address.getGeoPoint() == null (vì embedded lồng nhau dùng USE_NULL)
~~~

Điều này hữu ích khi domain muốn luôn có object để gọi các phương thức hoặc biểu diễn một nhóm giá trị chưa được cung cấp. Tuy nhiên, phải bảo đảm kiểu nhúng có thể được khởi tạo với các trường null/default.

### Chú ý kiểu primitive

Giả sử tọa độ khai báo:

~~~java
private double latitude;
private double longitude;
~~~

Java không có giá trị null cho `double`; nếu các cột tương ứng là SQL NULL và framework tạo object rỗng, các trường primitive có thể nhận giá trị mặc định `0.0`. Lúc này ứng dụng không phân biệt được:

- tọa độ chưa được cung cấp;
- tọa độ thực sự bằng 0.

Với các thuộc tính có thể null, nên dùng wrapper như `Double`, `Integer`, `Boolean` hoặc kiểu tham chiếu tương ứng. Dùng primitive khi miền nghiệp vụ bảo đảm giá trị luôn tồn tại và schema có ràng buộc phù hợp.

### USE_EMPTY không có nghĩa là tự tạo giá trị nghiệp vụ

`USE_EMPTY` chỉ dựng một instance từ dữ liệu rỗng; nó không tự điền địa chỉ mặc định, không gọi dịch vụ địa lý và không sinh giá trị như `"Unknown"`. Nếu cần giá trị mặc định, hãy đặt quy tắc rõ ràng ở constructor/factory hoặc application/domain service, và cân nhắc ảnh hưởng khi đọc dữ liệu cũ.

## 8. Đối tượng nhúng lồng nhau có chính sách riêng

Trong ví dụ, `shippingAddress` có thể tồn tại nhưng `geoPoint` có thể vắng mặt. Hai thuộc tính có hai phạm vi cột khác nhau:

- `shippingAddress` xét toàn bộ cột `shipping_street`, `shipping_city`, `shipping_geo_latitude` và `shipping_geo_longitude`.
- Khi Address đã được dựng, `geoPoint` xét riêng `shipping_geo_latitude` và `shipping_geo_longitude`.

Với outer `USE_NULL` và inner `USE_NULL`:

| Các cột shipping | Address | GeoPoint |
|---|---|---|
| Tất cả null | null | Không có parent để chứa GeoPoint |
| Street có giá trị; geo tất cả null | Object | null |
| Street có giá trị; một tọa độ có giá trị | Object | Object có trường còn lại null |
| Street và cả hai tọa độ có giá trị | Object | Object |

Nếu inner đổi thành `USE_EMPTY`, ở hàng thứ hai Address vẫn tồn tại và GeoPoint được tạo thành object rỗng. Nếu outer đổi thành `USE_EMPTY` và tất cả cột ngoài cùng đều null, Address vẫn được tạo; sau đó chính sách `onEmpty` của GeoPoint tiếp tục quyết định nested property.

**Cấp cha có thể ngăn việc quan sát cấp con:** khi Address được xác định là null, không có object Address để truy cập GeoPoint. Vì vậy, khi thiết kế lồng nhau, cần xét cả chính sách của outer lẫn inner; không chỉ đọc riêng annotation trên GeoPoint.

## 9. Phân biệt NULL với chuỗi rỗng và giá trị mặc định

Quy tắc `onEmpty` dựa trên **SQL NULL**, không phải “trường trông có vẻ rỗng”:

| Giá trị cột | Có được xem là SQL NULL? | Ảnh hưởng với USE_NULL |
|---|---|---|
| `NULL` | Có | Nếu tất cả cột trong embedded đều NULL, object là null |
| `''` | Không | Có ít nhất một cột khác NULL, object được tạo |
| `'   '` | Không | Object được tạo; chuỗi chứa dấu cách |
| Số `0` | Không | Object được tạo |
| Boolean `FALSE` | Không | Object được tạo |

Ví dụ, nếu `shipping_street = ''` nhưng các cột khác null, `shippingAddress` vẫn là một object vì street không phải SQL NULL. Nếu nghiệp vụ không chấp nhận chuỗi rỗng hoặc toàn dấu cách, hãy kiểm tra riêng bằng validation và/hoặc CHECK constraint.

Đừng dùng `USE_NULL` như một cơ chế tự động loại bỏ chuỗi rỗng. Hai khái niệm phục vụ hai mục đích khác nhau:

- `onEmpty` quyết định **có dựng object không** dựa trên null của toàn bộ nhóm cột.
- Validation quyết định **giá trị từng trường có hợp lệ không**, ví dụ street phải có nội dung.

## 10. Validation cho object nhúng một phần

Một Address có thể được ánh xạ thành object dù chỉ có street, nhưng quy tắc nghiệp vụ có thể yêu cầu street và city luôn đi cùng nhau. Ta có thể đặt kiểm tra ở factory/domain method:

~~~java
public static Address create(
        String street,
        String city,
        GeoPoint geoPoint) {
    if (street == null || street.isBlank()) {
        throw new IllegalArgumentException("Street is required");
    }
    if (city == null || city.isBlank()) {
        throw new IllegalArgumentException("City is required");
    }
    return new Address(street, city, geoPoint);
}
~~~

Đối với dữ liệu đọc từ database, constructor/factory mapping cần tương thích với trạng thái nullable mà schema cho phép. Nếu dữ liệu cũ có thể thiếu city, không nên viết constructor bắt buộc city không null rồi kỳ vọng `USE_NULL` sẽ tự sửa dữ liệu. Thay vào đó:

1. Xác định cột nào được phép null theo hợp đồng dữ liệu.
2. Dựng object với trạng thái tương ứng.
3. Kiểm tra tính hợp lệ ở use case cần sử dụng địa chỉ, hoặc migration dữ liệu cũ trước khi siết ràng buộc.
4. Khi ghi mới, validate để không tạo thêm trạng thái một phần mà domain không chấp nhận.

Nếu tất cả cột của embedded bắt buộc phải có giá trị khi object tồn tại, có thể dùng ràng buộc SQL để buộc các trường đi cùng nhau. Ví dụ PostgreSQL:

~~~sql
ALTER TABLE customer_profiles
ADD CONSTRAINT ck_shipping_address_complete
CHECK (
    (shipping_street IS NULL AND shipping_city IS NULL)
    OR
    (shipping_street IS NOT NULL AND shipping_city IS NOT NULL)
);
~~~

Ràng buộc trên chỉ minh họa một quy tắc: street và city cùng vắng mặt hoặc cùng có giá trị. Nó chưa quy định tọa độ phải tồn tại. Hãy thiết kế CHECK đúng với chính sách thực tế; tránh tạo ràng buộc vô tình cấm trạng thái mà nghiệp vụ cho phép.

## 11. Khi nào không thể phân biệt các trạng thái chỉ bằng embedded columns?

Giả sử cần phân biệt hai tình huống:

1. Người dùng **chưa tạo địa chỉ**.
2. Người dùng **đã tạo một Address**, nhưng mọi trường hiện đều trống vì một quy trình nhập liệu đang chờ hoàn tất.

Nếu cả hai tình huống đều lưu tất cả cột `shipping_*` thành SQL NULL, dữ liệu vật lý hoàn toàn giống nhau. Không có thuật toán đọc nào có thể khôi phục ý nghĩa đã không được lưu.

Có ba cách thiết kế:

- **Chấp nhận gộp hai trạng thái:** dùng `USE_NULL` nếu object toàn-null có nghĩa là không có object.
- **Dùng USE_EMPTY:** nếu object toàn-null khi đọc luôn được hiểu là một instance rỗng, không cần biết trước đó người dùng đã tạo nó hay chưa.
- **Lưu cờ hiện diện (presence flag):** thêm cột như `shipping_present BOOLEAN NOT NULL` để phân biệt object vắng mặt với object tồn tại nhưng các thuộc tính chưa có giá trị.

Ví dụ với presence flag:

~~~sql
ALTER TABLE customer_profiles
ADD COLUMN shipping_present BOOLEAN NOT NULL DEFAULT FALSE;
~~~

Khi đó, domain cần mapping và xử lý `shipping_present` rõ ràng. Chỉ thêm cột mà không sử dụng nó trong logic dựng object thì chưa giải quyết được bài toán. Một lựa chọn khác là dùng bảng riêng nếu địa chỉ có vòng đời, identity hoặc quan hệ riêng.

## 12. Repository đọc và ghi embedded object

Vì Address và GeoPoint là value object nhúng, repository được định nghĩa cho entity chứa chúng:

~~~java
package com.example.profile;

import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, Long> {
}
~~~

Lưu profile:

~~~java
Address address = new Address(
    "12 Nguyễn Trãi",
    "Hà Nội",
    new GeoPoint(21.0285, 105.8542)
);

CustomerProfile profile = new CustomerProfile(
    "Nguyễn An",
    address,
    null
);

CustomerProfile saved = repository.save(profile);
Long id = saved.getId();
~~~

Đọc lại:

~~~java
CustomerProfile loaded = repository.findById(id)
    .orElseThrow();

Address shipping = loaded.getShippingAddress();
if (shipping != null) {
    System.out.println(shipping.getStreet());

    GeoPoint point = shipping.getGeoPoint();
    if (point != null) {
        System.out.println(point.getLatitude());
        System.out.println(point.getLongitude());
    }
}
~~~

`findById` tải entity cùng các giá trị embedded theo mapping cột của nó. Không có thao tác join bảng địa chỉ vì các cột nằm trong cùng bảng. Repository không cần `AddressRepository` hoặc `GeoPointRepository`.

Với class mutable trong ví dụ, `save` trả về entity được lưu; hãy tiếp tục sử dụng giá trị trả về, nhất là khi ID được database sinh. `@Embedded` không làm thay đổi nguyên tắc này.

## 13. Kiểm tra trực tiếp dữ liệu SQL

Truy vấn các cột để quan sát trạng thái toàn-null và null một phần:

~~~sql
SELECT
    id,
    display_name,
    shipping_street,
    shipping_city,
    shipping_geo_latitude,
    shipping_geo_longitude,
    CASE
        WHEN shipping_street IS NULL
         AND shipping_city IS NULL
         AND shipping_geo_latitude IS NULL
         AND shipping_geo_longitude IS NULL
        THEN 'ALL_NULL'
        ELSE 'HAS_VALUE'
    END AS shipping_state
FROM customer_profiles
ORDER BY id;
~~~

Đối với nested GeoPoint, chỉ xét hai cột tọa độ:

~~~sql
SELECT
    id,
    CASE
        WHEN shipping_geo_latitude IS NULL
         AND shipping_geo_longitude IS NULL
        THEN 'GEO_ALL_NULL'
        ELSE 'GEO_HAS_VALUE'
    END AS geo_state
FROM customer_profiles
ORDER BY id;
~~~

Các truy vấn này minh họa cách database biểu diễn trạng thái vật lý. Việc Java nhận được `null` hay object rỗng còn phụ thuộc `onEmpty` của từng cấp.

## 14. Lỗi thường gặp khi dùng embedded lồng nhau

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ một cột con null làm cả object null | Mất các trường còn giá trị | Chỉ toàn bộ cột embedded null mới kích hoạt `USE_NULL` |
| Nghĩ chuỗi rỗng tương đương SQL NULL | Object có thể được tạo dù chuỗi không có nội dung | Phân biệt `NULL`, `''` và chuỗi whitespace |
| Dùng `USE_EMPTY` nhưng kiểu nhúng không chấp nhận field null | Constructor/mapping có thể thất bại | Cho phép trạng thái rỗng hoặc dùng chính sách `USE_NULL` |
| Dùng primitive cho trường có thể null | Null bị biến thành default như 0/false hoặc không thể biểu diễn đúng | Dùng wrapper/reference type |
| Không đặt prefix khi nhúng cùng kiểu hai lần | Trùng tên cột hoặc mapping không rõ | Đặt prefix khác nhau cho từng property |
| Quên ghép prefix các cấp | Truy vấn nhầm tên cột | Prefix ngoài và trong tạo tên cột lồng nhau |
| Cho rằng embedded tạo bảng riêng | Thiết kế schema sai | Embedded flatten vào bảng chứa |
| Dùng embedded cho object có identity/vòng đời riêng | Ranh giới domain bị nhập nhằng | Cân nhắc entity/aggregate riêng và lưu ID |
| Dựa vào USE_NULL để validate địa chỉ | Object một phần vẫn được dựng | Validate các trường bắt buộc ở domain/service và DB |
| Cần phân biệt absent với empty nhưng mọi cột đều null | Không thể khôi phục trạng thái ban đầu | Dùng presence flag hoặc mô hình lưu trữ khác |

## 15. Bài tập thực hành

1. Tạo bảng `customer_profiles` theo schema ví dụ và ánh xạ `CustomerProfile` với `shippingAddress` dùng `USE_NULL`.
2. Insert một hàng có tất cả cột `shipping_*` là NULL. Đọc lại và xác nhận `getShippingAddress() == null`.
3. Insert một hàng chỉ có `shipping_street`. Đọc lại và xác nhận Address khác null, còn city và geoPoint null.
4. Insert một hàng có street và latitude nhưng longitude null. Xác nhận GeoPoint được tạo với một trường null.
5. Đổi `shippingAddress` sang `USE_EMPTY`. Đọc lại hàng đầu tiên và quan sát Address được tạo dù mọi cột null.
6. Đổi nested `geoPoint` sang `USE_EMPTY`. Với hàng có street nhưng hai cột tọa độ null, quan sát GeoPoint là object rỗng.
7. Thử lưu `shipping_street = ''` và `shipping_street = '   '`. Giải thích vì sao `USE_NULL` không coi hai giá trị này là null.
8. Nhúng `Address` thêm một lần cho địa chỉ thanh toán. Đặt prefix `billing_` và xác định các cột cuối cùng, bao gồm prefix của GeoPoint.
9. Thêm quy tắc domain bắt buộc street và city cùng tồn tại. Quyết định nên validate ở factory/service, CHECK constraint hay cả hai.
10. Đề xuất schema có `shipping_present` nếu cần phân biệt “chưa có địa chỉ” với “đã bắt đầu tạo địa chỉ nhưng chưa nhập trường nào”.

Khi làm bài, hãy kiểm tra đồng thời **giá trị trong database**, **cấu hình `onEmpty` ở cấp cha**, và **cấu hình `onEmpty` ở cấp con**. Đừng chỉ quan sát một thuộc tính Java rồi suy ra toàn bộ trạng thái dữ liệu.

## 16. Ghi nhớ

`@Embedded` biểu diễn value object bằng các cột được trải phẳng trong bảng của entity chứa nó. `USE_NULL` biến nhóm cột toàn SQL NULL thành thuộc tính Java null; `USE_EMPTY` dựng một instance ngay cả khi toàn bộ cột null. Khi một vài cột có giá trị, object được tạo và các thuộc tính còn thiếu được ánh xạ thành null/default tương ứng.

Với embedded lồng nhau, **mỗi cấp có prefix và quy tắc onEmpty riêng**. Prefix giúp tạo tên cột không xung đột; quy tắc cấp ngoài quyết định object cha có tồn tại, sau đó quy tắc cấp trong quyết định object con. Cuối cùng, `onEmpty` chỉ giải quyết việc dựng object từ trạng thái SQL NULL; nó không thay thế validation nghiệp vụ, không biến chuỗi rỗng thành null và không khôi phục được những trạng thái mà schema chưa lưu.
