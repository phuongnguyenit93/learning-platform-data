# Đường dẫn /{collection}/{id}/{property} cho quan hệ trong Spring Data REST

## Bối cảnh

Spring Data REST xuất bản các Spring Data repository thành REST resources. Ngoài collection resource và item resource, mỗi item còn có thể có các **association resources** để đọc hoặc thay đổi quan hệ giữa entity đó với entity khác.

Mẫu đường dẫn:

    /{collection}/{id}/{property}

Ví dụ:

    /orders/42/customer
    /people/42/addresses

Đây là mẫu URI minh họa. Các dấu ngoặc nhọn biểu thị phần cần thay bằng giá trị thật; không gửi nguyên chuỗi có dấu ngoặc nhọn lên server. Association resource giúp client thao tác với quan hệ thông qua HTTP mà không cần tự tạo một controller riêng cho từng association.

Sau bài này, bạn có thể đọc đúng ba phần của URI, tìm association link từ HAL response, gọi các HTTP method phù hợp và nhận biết những nguyên nhân phổ biến khiến endpoint không hoạt động.

## 1. Ý nghĩa của từng phần trong URI

| Phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| collection | Đường dẫn collection resource của repository chứa entity cha | orders |
| id | Định danh của item resource cha đang giữ quan hệ | 42 |
| property | Tên association property trên entity cha; mặc định dùng tên property trong domain model | customer |

Giả sử có một đơn hàng mang ID 42 và property customer trỏ tới khách hàng của đơn hàng đó. Association resource có thể nằm tại:

    /orders/42/customer

Trong ví dụ này:

- orders là collection path của repository đơn hàng.
- 42 là ID của đơn hàng, tức entity cha.
- customer là association property trên entity đơn hàng.

Điểm dễ nhầm nhất là id trong mẫu đường dẫn thuộc về **entity cha**. Nó không phải ID của entity được liên kết. ID của khách hàng được truyền qua URI của khách hàng khi gán quan hệ.

Collection path cũng không nhất thiết trùng tên class, tên bảng hoặc tên collection trong database. Spring Data REST có quy tắc đặt tên mặc định, nhưng bạn có thể khai báo rõ bằng @RepositoryRestResource(path = "...").

## 2. Ví dụ domain model

Giả sử một đơn hàng có một khách hàng. Hai repository được Spring Data REST xuất bản như sau:

    @Entity
    public class PurchaseOrder {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne
        private Customer customer;

        // constructors, getters and setters
    }

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;

        // constructors, getters and setters
    }

    @RepositoryRestResource(path = "orders")
    public interface PurchaseOrderRepository
            extends JpaRepository<PurchaseOrder, Long> {
    }

    @RepositoryRestResource(path = "customers")
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Với cấu hình này, item resource của đơn hàng có dạng /orders/{id}; item resource của khách hàng có dạng /customers/{id}. Association property customer tạo ra association resource dưới item resource của đơn hàng.

Nếu đơn hàng 42 đang liên kết với khách hàng 7, các URI liên quan là:

    Item resource của đơn hàng:  /orders/42
    Association resource:        /orders/42/customer
    Item resource của khách hàng: /customers/7

Association resource và item resource của khách hàng là hai tài nguyên khác nhau. URI đầu tiên đại diện cho quan hệ customer của đơn hàng 42; URI thứ hai đại diện cho chính khách hàng 7.

## 3. Tìm association resource qua HAL

Khi client gọi item resource và yêu cầu HAL JSON, Spring Data REST trả về các liên kết của tài nguyên. Association link thường được đặt tên theo association property.

    GET http://localhost:8080/orders/42
    Accept: application/hal+json

Một response rút gọn có thể trông như sau:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders/42"
        },
        "purchaseOrder": {
          "href": "http://localhost:8080/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/orders/42/customer"
        }
      }
    }

Client lấy href của link customer để truy cập association resource. Tên quan hệ trong _links là HAL relation (rel); href là URI thực tế để gọi.

Hãy ưu tiên đi theo href mà server trả về thay vì tự ghép URI. Collection path, base path, association path và cách đặt rel đều có thể được tùy chỉnh. Khi các cấu hình đó thay đổi, link do server cung cấp vẫn là nguồn chỉ dẫn phù hợp cho client.

Đọc association resource:

    GET http://localhost:8080/orders/42/customer
    Accept: application/hal+json

GET trả về trạng thái hiện tại của association. Response có thể thể hiện tài nguyên được liên kết hoặc trạng thái quan hệ tùy representation và loại association.

## 4. Các HTTP method của association resource

Spring Data REST hỗ trợ GET, PUT, POST và DELETE cho association resource. Khả năng sử dụng từng method phụ thuộc vào kiểu quan hệ.

| Method | Mục đích | Phạm vi |
| --- | --- | --- |
| GET | Đọc trạng thái association | To-one và collection |
| PUT | Gán resource được chỉ định bởi URI vào association | To-one và association nhận URI |
| POST | Thêm một phần tử vào association | Chỉ collection association |
| DELETE | Gỡ liên kết association | Phụ thuộc tính optional của quan hệ |

### GET — đọc quan hệ

Dùng GET để xem association hiện tại:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/orders/42/customer

GET không có nghĩa là lấy toàn bộ entity cha. Nó truy cập riêng association resource được đặt dưới item resource.

### PUT — gán một quan hệ to-one

Với quan hệ to-one như ManyToOne hoặc OneToOne, PUT dùng URI của resource cần liên kết. Body có media type text/uri-list.

    curl -i -X PUT       -H "Content-Type: text/uri-list"       --data "http://localhost:8080/customers/7"       http://localhost:8080/orders/42/customer

Request này yêu cầu gán khách hàng có URI /customers/7 vào association customer của đơn hàng 42.

Không gửi JSON dạng {"id": 7} cho association endpoint này. API association dùng URI của resource đích, với Content-Type text/uri-list. Nếu association là to-one mà request gửi nhiều URI, server có thể trả về 400 Bad Request.

### POST — thêm phần tử vào collection association

Với collection association, chẳng hạn một người có nhiều địa chỉ, POST thêm một resource vào collection:

    curl -i -X POST       -H "Content-Type: text/uri-list"       --data "http://localhost:8080/addresses/10"       http://localhost:8080/people/42/addresses

Trong ví dụ này, 42 vẫn là ID của người sở hữu quan hệ; 10 là ID của địa chỉ được thêm vào. POST dành cho collection association, không dùng để gán một quan hệ to-one.

Có thể gửi nhiều URI trong text/uri-list, mỗi URI trên một dòng, khi association và thao tác cho phép nhiều phần tử.

### DELETE — gỡ liên kết

DELETE yêu cầu server gỡ association:

    curl -i -X DELETE       http://localhost:8080/orders/42/customer

Thao tác này gỡ liên kết customer khỏi đơn hàng 42; nó không đồng nghĩa với việc xóa bản ghi Customer khỏi database. Nếu quan hệ được cấu hình bắt buộc, không cho phép để trống, Spring Data REST có thể từ chối thao tác và trả về 405 Method Not Allowed.

Luôn kiểm tra mapping domain, ràng buộc database và quyền truy cập trước khi thực hiện thao tác thay đổi hoặc gỡ liên kết trên dữ liệu thật.

## 5. Tùy chỉnh association path và HAL relation

Mặc định, tên và path của association resource lấy từ tên association property. Bạn có thể tùy chỉnh bằng @RestResource trên property.

    @Entity
    public class PurchaseOrder {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne
        @RestResource(path = "buyer", rel = "buyer")
        private Customer customer;
    }

Với cấu hình này, association path được đổi thành buyer:

    /orders/42/buyer

HAL relation cũng có tên buyer. Hai thuộc tính có vai trò riêng:

- path quyết định segment URL của association resource.
- rel quyết định tên liên kết trong _links của HAL response.

Nếu chỉ đổi tên property trong Java, hãy kiểm tra lại URI và HAL relation thực tế. Khi API đã được client sử dụng, việc đổi path hoặc rel có thể ảnh hưởng tương thích ngược.

Bạn cũng có thể ẩn association khỏi REST API bằng cấu hình exported = false trên association property:

    @ManyToOne
    @RestResource(exported = false)
    private Customer customer;

Khi association không được xuất bản, client không nên kỳ vọng tìm thấy association link tương ứng.

## 6. Base path và URI đầy đủ

Nếu ứng dụng cấu hình base path:

    spring.data.rest.base-path=/api

thì URI có thể có dạng:

    /api/orders/42/customer

Base path là tiền tố chung của các resource Spring Data REST. Context path của servlet, reverse proxy hoặc gateway cũng có thể làm thay đổi URI bên ngoài mà client nhìn thấy.

Vì vậy, không nên cố định chuỗi /orders/42/customer trong mọi client. Hãy đọc link từ HAL response để lấy href đã được server tạo theo cấu hình đang chạy.

## 7. Phân biệt association resource với item resource

Hai URI sau không có cùng ý nghĩa:

    /orders/42
    /orders/42/customer

/orders/42 là item resource của một đơn hàng. Client đọc hoặc cập nhật dữ liệu của đơn hàng tại đây.

/orders/42/customer là association resource đại diện cho quan hệ customer của đơn hàng đó. Client dùng endpoint này để đọc hoặc thay đổi liên kết.

Trong khi đó:

    /customers/7

là item resource của khách hàng 7. Đây thường là URI được truyền trong body text/uri-list khi muốn gán khách hàng đó vào association.

Việc phân biệt ba URI này giúp tránh lỗi phổ biến: dùng ID của entity đích ở segment {id} hoặc gửi dữ liệu entity thay cho URI của resource đích.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
| --- | --- |
| 404 Not Found | Sai collection path, ID entity cha, association path; repository hoặc association chưa được xuất bản |
| Không thấy link trong _links | Association không linkable, bị ẩn bằng exported = false, repository liên quan không được xuất bản hoặc rel/path đã được tùy chỉnh |
| 405 Method Not Allowed | Method không được hỗ trợ cho kiểu association hoặc DELETE bị từ chối vì quan hệ không optional |
| 400 Bad Request khi PUT | Gửi nhiều URI cho quan hệ to-one |
| 415 Unsupported Media Type | Dùng JSON thay cho text/uri-list khi gọi PUT hoặc POST association |
| 403 Forbidden | Spring Security không cho phép principal hiện tại đọc hoặc thay đổi resource |
| Quan hệ không được lưu như mong đợi | Kiểm tra owning side, helper đồng bộ hai chiều và transaction của mapping JPA |

Khi debug, thực hiện theo thứ tự:

1. GET item resource của entity cha và kiểm tra response HAL.
2. Lấy đúng href từ association link.
3. GET href đó để xác nhận association resource tồn tại.
4. Kiểm tra method, Content-Type và body URI.
5. Kiểm tra log server, cấu hình export, security và mapping persistence nếu response vẫn không như mong đợi.

Không kết luận endpoint không tồn tại chỉ vì bạn đoán sai tên property. Hãy kiểm tra link thực tế do server trả về.

## 9. Lưu ý về persistence và bảo mật

Association resource là cách Spring Data REST biểu diễn quan hệ trong domain model; nó không phải đường dẫn đến cột foreign key hay tên bảng trong database.

Với JPA, hãy xác định phía sở hữu quan hệ (owning side). Ví dụ, nếu foreign key nằm ở bảng orders thì property customer trên PurchaseOrder thường là phía sở hữu của quan hệ ManyToOne. Khi quan hệ hai chiều, nên dùng helper method để đồng bộ cả hai phía trong bộ nhớ trước khi lưu, tránh trạng thái object graph không nhất quán.

Việc Spring Data REST hiển thị association link cũng không tự động cấp quyền cho mọi người dùng. Cấu hình Spring Security vẫn quyết định ai được GET, PUT, POST hoặc DELETE. Client cần xử lý 401/403 và không được coi việc nhìn thấy href là bằng chứng rằng thao tác ghi chắc chắn được phép.

## 10. Bài thực hành

Giả sử API có các resource:

- Đơn hàng 42 tại /orders/42.
- Khách hàng 7 tại /customers/7.
- Association customer của đơn hàng 42 tại /orders/42/customer.

Thực hiện lần lượt:

1. Gọi GET /orders/42 với Accept: application/hal+json.
2. Tìm link customer trong _links và đọc href.
3. Gọi GET href đó để xem khách hàng hiện đang được liên kết.
4. Gọi PUT tới association href, Content-Type: text/uri-list, body là URI /customers/7.
5. Gọi GET association href lần nữa để xác nhận quan hệ đã đổi.
6. Thử gửi hai URI cho association to-one và quan sát lỗi 400.
7. Thử DELETE trong môi trường dữ liệu thử nghiệm, sau đó xác nhận quan hệ đã được gỡ; nếu server trả 405, kiểm tra quan hệ có bắt buộc hay không.

Câu hỏi tự kiểm tra:

- Trong /orders/42/customer, ID 42 thuộc entity nào?
- URI /customers/7 có vai trò gì khi gọi PUT?
- Vì sao POST chỉ phù hợp với collection association?
- path và rel trong @RestResource khác nhau ở điểm nào?
- Vì sao nên dùng href trong HAL thay vì tự ghép URL?

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources và Association Resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
