# Ảnh hưởng của việc có repository riêng đến cách biểu diễn quan hệ

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao một thuộc tính quan hệ trong Spring Data REST đôi khi xuất hiện dưới dạng link HAL và đôi khi xuất hiện như một object lồng trong JSON; tạo ví dụ có và không có repository cho entity liên quan; đọc và cập nhật association resource; và chọn cách biểu diễn phù hợp bằng projection, excerpt projection hoặc cấu hình export.

## 1. Hai khái niệm cần tách biệt

Trong mô hình miền, một entity có thể tham chiếu đến entity khác. Ví dụ, Person có thuộc tính address kiểu Address. Với JPA, quan hệ này có thể được ánh xạ bằng @OneToOne, @ManyToOne, @OneToMany hoặc @ManyToMany.

Spring Data REST dùng repository để quyết định những domain type nào được xuất bản thành REST resource. Vì vậy cần phân biệt:

- **Mapping quan hệ** mô tả cách các object liên kết và được lưu trữ, ví dụ @OneToOne hoặc @ManyToOne.
- **Repository** cho biết một domain type có một cổng truy cập dữ liệu riêng hay không.
- **Export repository** quyết định Spring Data REST có công bố repository đó thành các collection/item resources cho HTTP client hay không.

Chỉ có annotation quan hệ JPA không tự tạo ra một REST endpoint độc lập cho entity được tham chiếu. Ngược lại, có repository riêng cho entity liên quan có thể làm thay đổi cách Spring Data REST biểu diễn thuộc tính quan hệ trong HAL.

## 2. Ví dụ miền Person và Address

Giả sử ứng dụng có hai entity. Các đoạn mã sau tập trung vào phần liên quan; constructor, getter, setter và import được lược bỏ:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;

    @OneToOne
    private Address address;
}
~~~

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String street;
    private String country;
}
~~~

Repository của Person:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Giả sử dữ liệu có một người tên Frodo và địa chỉ Bag End. Ta sẽ thay đổi duy nhất việc có hay không có AddressRepository để quan sát kết quả.

## 3. Trường hợp không có repository riêng cho Address

Nếu ứng dụng chỉ có PersonRepository, Spring Data REST không có repository resource riêng để quản lý Address. Theo cách biểu diễn mặc định, dữ liệu của Address được đưa trực tiếp vào representation của Person.

Ví dụ phản hồi HAL rút gọn từ GET /persons/1:

~~~json
{
  "firstName": "Frodo",
  "address": {
    "street": "Bag End",
    "country": "Middle Earth"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1"
    }
  }
}
~~~

Trong trường hợp này:

- Client nhận được các trường của Address ngay trong response của Person.
- Không có collection resource /addresses được tạo ra từ một AddressRepository.
- Client không thể dựa vào Spring Data REST để duyệt tới một Address item resource độc lập theo cách thông thường.
- Khi cần đọc hoặc cập nhật dữ liệu địa chỉ, client làm việc thông qua representation và endpoint của Person, theo cấu trúc dữ liệu mà API chấp nhận.

Cách này phù hợp khi Address chỉ là một phần dữ liệu phụ thuộc vào Person, không cần được tra cứu, tham chiếu hoặc quản lý như một resource độc lập.

## 4. Trường hợp có repository riêng cho Address

Thêm một repository cho Address:

~~~java
public interface AddressRepository
        extends CrudRepository<Address, Long> {
}
~~~

Spring Data REST giờ có thể xuất bản cả hai loại resource:

- Collection resource cho Person, mặc định là /persons.
- Collection resource cho Address, mặc định là /addresses.

Một Person item vẫn được truy cập tại /persons/1. Nhưng trong representation của Person, thuộc tính address được thể hiện bằng association link thay vì nhúng toàn bộ các trường của Address.

Ví dụ HAL rút gọn:

~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1"
    },
    "address": {
      "href": "http://localhost:8080/persons/1/address"
    }
  }
}
~~~

Điểm cần chú ý là link address trong ví dụ trỏ đến **association resource** /persons/1/address. Nó đại diện cho quan hệ address của Person đó. Repository riêng cho Address cũng làm cho collection và các item resource của Address có thể được khám phá từ API root, ví dụ /addresses và /addresses/5.

Có thể đọc quan hệ qua link được cung cấp:

~~~http
GET /persons/1/address
Accept: application/hal+json
~~~

Association resource trả về trạng thái hiện tại của quan hệ. Khi cần gắn một Address đã tồn tại vào Person, client gửi URI của Address resource đến association resource.

Với quan hệ một-một hoặc nhiều-một, ví dụ gắn Address số 5:

~~~http
PUT /persons/1/address
Content-Type: text/uri-list

http://localhost:8080/addresses/5
~~~

Với association dạng collection, POST vào association resource để thêm một phần tử. DELETE dùng để bỏ liên kết; thao tác bỏ liên kết còn phụ thuộc quan hệ có cho phép rỗng hay không. PUT cho quan hệ một-một không nhận nhiều URI cùng lúc.

Cách biểu diễn bằng link hữu ích khi entity liên quan có vòng đời hoặc cách truy cập riêng, được nhiều entity khác tham chiếu, hoặc có thể có nhiều dữ liệu. Client có thể tải dữ liệu liên quan khi cần thay vì luôn nhận toàn bộ object lồng nhau.

## 5. So sánh trực tiếp

| Khía cạnh | Không có AddressRepository | Có AddressRepository được export |
|---|---|---|
| Biểu diễn address trong Person | Object lồng trong JSON | Link quan hệ trong _links |
| Dữ liệu địa chỉ trong response Person mặc định | Các trường địa chỉ được gửi inline | Không gửi toàn bộ trường địa chỉ theo mặc định |
| Resource /addresses | Không được tạo từ repository | Được công bố |
| Truy cập quan hệ | Qua dữ liệu của Person | Theo association link, ví dụ /persons/1/address |
| Quản lý Address độc lập qua Spring Data REST | Không có repository resource riêng | Có thể truy cập collection/item Address resources |
| Kích thước response Person | Có thể lớn hơn khi object liên quan có nhiều trường | Thường gọn hơn; client có thể cần request bổ sung |

Đây là hành vi biểu diễn mặc định. Projection, excerpt projection, Jackson configuration và các tùy chỉnh khác có thể thay đổi nội dung response.

## 6. Repository riêng không đồng nghĩa luôn phải trả về link

Bạn có thể muốn giữ repository riêng để Address có endpoint độc lập, nhưng vẫn muốn gửi một số trường địa chỉ cùng response Person. Spring Data REST hỗ trợ projection để điều chỉnh representation.

### 6.1. Projection để chọn trường được trả về

Ví dụ projection chỉ trả về tên, không đưa địa chỉ vào phần dữ liệu:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();
}
~~~

Có thể yêu cầu representation này qua query parameter:

~~~http
GET /persons/1?projection=personSummary
Accept: application/hal+json
~~~

Projection xác định những thuộc tính được đưa vào representation. Các association link do Spring Data REST cung cấp vẫn có thể hiện diện để client khám phá quan hệ.

Để một projection được tự động phát hiện, đặt interface cùng package với domain type hoặc trong sub-package; nếu cần, đăng ký thủ công qua RepositoryRestConfiguration.

### 6.2. Excerpt projection để nhúng dữ liệu thường dùng

Nếu client thường xuyên cần đọc địa chỉ cùng Person, có thể định nghĩa projection chứa getAddress():

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    Address getAddress();
}
~~~

Sau đó gắn làm excerpt projection cho repository:

~~~java
@RepositoryRestResource(excerptProjection = PersonWithAddress.class)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Excerpt projection được dùng khi Spring Data REST nhúng Person vào collection hoặc related resources. Representation khi đó có thể vừa chứa object address inline, vừa giữ association link để client tiếp tục điều hướng đến resource Address.

Excerpt projection không tự động áp dụng cho mọi response của một item resource đơn lẻ. Khi cần một projection cụ thể cho item, hãy yêu cầu rõ qua ?projection=personWithAddress.

### 6.3. Đổi tên hoặc ẩn association link

Có thể đổi tên relation và path bằng @RestResource trên thuộc tính:

~~~java
@OneToOne
@RestResource(path = "location", rel = "location")
private Address address;
~~~

Link quan hệ lúc này dùng relation/path location theo cấu hình.

Nếu không muốn xuất bản association property, có thể dùng @RestResource(exported = false) trên thuộc tính:

~~~java
@OneToOne
@RestResource(exported = false)
private Address address;
~~~

Nếu muốn ẩn toàn bộ REST repository của một domain type, có thể đặt @RepositoryRestResource(exported = false) trên repository. Repository vẫn có thể được dùng trong ứng dụng qua Spring Data, nhưng Spring Data REST không công bố repository đó như REST resource.

Ẩn association và ẩn repository là hai quyết định ở hai phạm vi khác nhau. Hãy kiểm tra API thực tế sau khi cấu hình, đặc biệt khi client đang phụ thuộc vào link hoặc endpoint cũ.

## 7. Chọn cách thiết kế phù hợp

Dùng repository riêng cho entity liên quan khi:

- Entity có định danh và vòng đời độc lập.
- Nhiều entity khác cùng tham chiếu đến entity đó.
- Client cần tìm kiếm, phân trang, cập nhật hoặc xóa entity liên quan độc lập.
- Bạn muốn API có link HATEOAS rõ ràng để điều hướng giữa các resource.

Không nhất thiết tạo repository riêng khi:

- Object chỉ là thành phần phụ thuộc, luôn được đọc và cập nhật cùng aggregate cha.
- Không cần endpoint độc lập cho object.
- Việc trả các trường object lồng nhau là phù hợp với hợp đồng API.

Khi chọn representation, cân nhắc số lượng trường, số lượng quan hệ, tần suất client cần dữ liệu liên quan và chi phí của các request bổ sung. Với object lớn hoặc quan hệ nhiều tầng, link và projection thường giúp kiểm soát response tốt hơn. Với object nhỏ, ổn định và thường được dùng cùng entity cha, inline representation có thể thuận tiện hơn.

Không nên quyết định repository chỉ dựa trên việc muốn JSON ngắn hay dài. Repository còn ảnh hưởng đến khả năng khám phá, định tuyến và thao tác resource. Hãy thiết kế ranh giới repository theo cách domain cần được truy cập và quản lý.

## 8. Lỗi thường gặp

1. **Cho rằng @OneToOne tự tạo endpoint cho Address.** Annotation JPA mô tả quan hệ persistence; muốn Address có collection/item resource trong Spring Data REST, cần repository được export.
2. **Nhầm association link với link item trực tiếp.** Trong ví dụ, _links.address trỏ đến /persons/1/address, là endpoint của association trên Person. Item Address có URI riêng, ví dụ /addresses/5.
3. **Tưởng có repository riêng thì không thể nhúng dữ liệu liên quan.** Projection hoặc excerpt projection có thể đưa các trường cần thiết vào representation và vẫn giữ link.
4. **Dùng exported = false sai phạm vi.** Đặt trên association property sẽ ẩn quan hệ đó; đặt trên repository sẽ ẩn repository resource. Hai cấu hình có tác động khác nhau.
5. **Gửi JSON object khi association endpoint yêu cầu URI.** Các thao tác bind association resource dùng text/uri-list với URI của resource đích.
6. **Không kiểm tra thay đổi hợp đồng API.** Chuyển từ inline object sang link làm thay đổi cấu trúc response mà client phải xử lý. Cần cập nhật và kiểm thử consumer trước khi phát hành.
7. **Để projection trả ra quá nhiều dữ liệu.** Projection có thể làm response lớn và tăng chi phí truy xuất. Chỉ đưa các trường client thực sự cần vào representation.

## 9. Quy trình kiểm tra trong ứng dụng

1. Tạo PersonRepository và chạy ứng dụng; gọi GET /persons/1 để quan sát representation khi chưa có AddressRepository.
2. Thêm AddressRepository, khởi động lại và gọi lại cùng endpoint. So sánh address inline với _links.address.
3. Theo link association trong response bằng GET /persons/1/address.
4. Thử gắn một Address đã tồn tại bằng PUT và Content-Type: text/uri-list.
5. Thêm projection hoặc excerpt projection, gọi endpoint tương ứng và kiểm tra cả phần dữ liệu inline lẫn link.
6. Kiểm tra API root, endpoint và quyền truy cập để chắc chắn chỉ các repository và association mong muốn được công bố.

## 10. Tài liệu tham khảo

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository Resources and Association Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST — Hiding Repositories, Query Methods, and Fields](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)

Các ví dụ representation được rút gọn để làm nổi bật khác biệt giữa inline data và association link. URI thực tế phụ thuộc vào context path, cấu hình @RepositoryRestResource, @RestResource và cấu hình export của ứng dụng.
