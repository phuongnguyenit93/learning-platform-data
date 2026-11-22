# Quan hệ bắt buộc, URI không tồn tại và lỗi số lượng tham chiếu trong Spring Data REST

Spring Data REST xuất bản các repository thành tài nguyên HTTP và biểu diễn quan hệ giữa entity bằng các liên kết hypermedia. Khi đọc một tài nguyên, client thường nhận được các liên kết trong mục `_links`; khi cập nhật quan hệ, client gửi URI của tài nguyên liên quan đến endpoint association. Vì vậy, một lỗi liên kết có thể xuất phát từ ba lớp khác nhau: quy tắc quan hệ trong mô hình dữ liệu, URI mà client gửi và số lượng phần tử mà kiểu quan hệ cho phép.

Bài này dùng ví dụ `Order` có một `Customer` bắt buộc và một `Article` có nhiều `Tag`. Các đường dẫn dùng tiền tố `/api` để minh họa; đường dẫn thực tế phụ thuộc base path, tên repository và cấu hình `@RestResource`.

## 1. Nhận diện association resource và URI tham chiếu

Giả sử client đọc:

    GET /api/orders/42
    Accept: application/hal+json

Phản hồi HAL có thể chứa liên kết đến đơn hàng và association khách hàng:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/api/orders/42/customer"
        }
      }
    }

Hai URI có vai trò khác nhau:

- URI của entity, chẳng hạn `/api/customers/7`, định danh tài nguyên Customer được tham chiếu.
- URI association, chẳng hạn `/api/orders/42/customer`, là endpoint dùng để đọc hoặc thay đổi quan hệ customer của Order 42.

Client nên lấy liên kết từ phản hồi HAL thay vì tự ghép tên quan hệ hoặc đoán đường dẫn. Tên quan hệ và path có thể được tùy chỉnh bằng `@RestResource`; association cũng có thể không được xuất bản nếu cấu hình repository hoặc association không cho phép truy cập.

Khi gửi một tham chiếu, Spring Data REST thường nhận URI qua media type `text/uri-list`. Nội dung là URI đầy đủ của tài nguyên đích, không phải ID dạng số và cũng không phải JSON mô tả entity.

## 2. Khai báo quan hệ bắt buộc đúng ở nhiều lớp

Ví dụ một đơn hàng phải thuộc về đúng một khách hàng:

    @Entity
    public class Order {
        @Id
        @GeneratedValue
        private Long id;

        @NotNull
        @ManyToOne(fetch = FetchType.LAZY, optional = false)
        @JoinColumn(name = "customer_id", nullable = false)
        private Customer customer;

        // getters và setters
    }

Ba khai báo trong ví dụ bảo vệ các lớp khác nhau:

- `@NotNull` là ràng buộc Bean Validation. Nó giúp phát hiện entity thiếu customer trước khi thao tác lưu hoàn tất, nếu validator được chạy trong luồng repository.
- `optional = false` thể hiện quan hệ bắt buộc theo mô hình JPA.
- `nullable = false` yêu cầu cột khóa ngoại không nhận NULL khi schema được tạo từ mapping. Nếu database được quản lý bằng migration, migration cũng phải tạo cột NOT NULL và foreign key tương ứng.

Không nên coi riêng `optional = false` là thông báo lỗi API thân thiện. Mapping JPA và ràng buộc database bảo vệ tính toàn vẹn dữ liệu, còn Bean Validation giúp trả lỗi sớm và dễ hiểu hơn. Cần bảo đảm cả ba lớp nhất quán với quy tắc nghiệp vụ.

Với Spring Boot 3, dùng Jakarta Bean Validation, thường thông qua dependency `spring-boot-starter-validation`. Spring Data REST có thể chạy validator ở các sự kiện repository như `beforeCreate` và `beforeSave`:

    @Configuration
    public class RepositoryValidationConfiguration {
        @Bean
        ValidatingRepositoryEventListener validatingRepositoryEventListener(
                jakarta.validation.Validator validator) {
            var listener = new ValidatingRepositoryEventListener();
            listener.addValidator("beforeCreate", validator);
            listener.addValidator("beforeSave", validator);
            return listener;
        }
    }

Nếu dự án đã có cấu hình listener tương đương, hãy bổ sung validator vào cấu hình hiện tại thay vì đăng ký listener trùng lặp. Với association được cập nhật qua endpoint riêng, hãy kiểm thử rằng luồng cập nhật thực sự chạy validation trên entity cần bảo vệ.

### Gửi và gỡ một quan hệ đơn

Gán Customer 7 cho Order 42:

    PUT /api/orders/42/customer
    Content-Type: text/uri-list

    http://localhost:8080/api/customers/7

Client phải dùng URI của Customer đã được repository xuất bản. Nếu quan hệ là bắt buộc, yêu cầu xóa liên kết:

    DELETE /api/orders/42/customer

phải bị từ chối bởi quy tắc validation hoặc ràng buộc lưu trữ. Nếu chỉ dựa vào NOT NULL ở database, lỗi có thể xuất hiện muộn trong lúc lưu và thông báo thường khó giải thích hơn.

## 3. URI không tồn tại hoặc không thể phân giải

Một URI có cú pháp hợp lệ chưa chắc trỏ đến một tài nguyên đang tồn tại. Ví dụ:

    PUT /api/orders/42/customer
    Content-Type: text/uri-list

    http://localhost:8080/api/customers/999999

Nếu Customer 999999 không tồn tại, Spring Data REST không thể thiết lập tham chiếu đến entity đích. Trường hợp này khác với việc gửi một chuỗi không phải URI hoặc gửi sai định dạng body.

Khi gặp lỗi tham chiếu, kiểm tra lần lượt:

1. URI có đúng cú pháp và đúng host/base path của API không?
2. Repository đích có được xuất bản và endpoint có đúng tên không?
3. Entity đích có tồn tại với ID đó không?
4. Client có quyền đọc hoặc liên kết tài nguyên đích theo cấu hình bảo mật không?
5. URI có trỏ đến đúng loại tài nguyên mà thuộc tính association mong đợi không?

Một số tình huống thường gặp:

| Tình huống | Kết quả thường gặp | Cách xử lý |
|---|---|---|
| Body không phải URI hợp lệ hoặc sai media type | 400 Bad Request | Gửi URI hợp lệ và `Content-Type: text/uri-list` |
| URI đúng cú pháp nhưng entity đích không tồn tại | 404 Not Found | Kiểm tra ID và đọc tài nguyên đích trước khi liên kết |
| Repository hoặc association không được xuất bản | 404 Not Found hoặc endpoint không có trong HAL | Kiểm tra cấu hình repository và `@RestResource` |
| Người gọi không được phép truy cập | 401 Unauthorized hoặc 403 Forbidden | Kiểm tra xác thực và quyền |
| Entity vi phạm ràng buộc bắt buộc | Thường là lỗi validation 400; lỗi database phụ thuộc exception mapping | Bổ sung validation và giữ ràng buộc database |

Mã HTTP cụ thể có thể chịu ảnh hưởng bởi phiên bản Spring Data REST, exception handler và cấu hình bảo mật. Khi thiết kế client, hãy dựa vào response body và mã lỗi thực tế của API đang chạy; không chuyển mọi lỗi liên kết thành thông báo “không tìm thấy ID”.

## 4. Hiểu đúng số lượng tham chiếu theo cardinality

Số URI được gửi phải phù hợp với kiểu thuộc tính association. Cardinality của quan hệ trong JPA quyết định một entity có thể tham chiếu bao nhiêu entity khác; nó không tự động đặt ra mọi giới hạn nghiệp vụ như “ít nhất hai tag” hoặc “không quá năm dòng hàng”.

| Mapping JPA | Ý nghĩa ở phía entity hiện tại | Số tham chiếu |
|---|---|---|
| `@OneToOne` | Một entity liên kết tối đa với một entity đích | Một URI hoặc không có nếu quan hệ tùy chọn |
| `@ManyToOne` | Nhiều entity nguồn có thể cùng trỏ đến một entity đích | Một URI cho mỗi entity nguồn |
| `@OneToMany` | Một entity nguồn có thể có nhiều entity con | Một collection URI |
| `@ManyToMany` | Một entity có thể liên kết với nhiều entity ở phía kia | Một collection URI |

Ví dụ, một Article có thể có nhiều Tag:

    @Entity
    public class Article {
        @Id
        @GeneratedValue
        private Long id;

        @ManyToMany
        private Set<Tag> tags = new HashSet<>();

        // getters và setters
    }

Để thêm một hoặc nhiều tag vào association collection, client gửi danh sách URI:

    POST /api/articles/42/tags
    Content-Type: text/uri-list

    http://localhost:8080/api/tags/3
    http://localhost:8080/api/tags/8

Với collection association, POST thường dùng để thêm tham chiếu; DELETE cùng URI trong body dùng để gỡ các tham chiếu được chỉ định:

    DELETE /api/articles/42/tags
    Content-Type: text/uri-list

    http://localhost:8080/api/tags/8

Ngược lại, association đơn như `Order.customer` chỉ nhận một URI. Gửi nhiều dòng URI cho thuộc tính đơn là sai cardinality; không chuyển một quan hệ đơn thành collection chỉ bằng cách gửi nhiều ID.

Lưu ý về JPA: với quan hệ hai chiều, phía sở hữu (owning side) mới quyết định cập nhật khóa ngoại hoặc bảng nối. Ví dụ `mappedBy` đánh dấu phía inverse; chỉ sửa collection ở phía inverse mà không cập nhật owning side có thể khiến quan hệ không được lưu như mong đợi. Hãy kiểm tra mapping và kiểm thử endpoint association sau khi đọc lại tài nguyên.

## 5. Ràng buộc số lượng tối thiểu, tối đa và tính duy nhất

Các annotation quan hệ mô tả cấu trúc liên kết, nhưng thường không diễn đạt đầy đủ giới hạn số phần tử của nghiệp vụ:

- `@OneToMany` không có nghĩa collection bắt buộc phải chứa ít nhất một phần tử.
- `@ManyToMany` không tự đặt giới hạn tối đa cho số liên kết.
- `@ManyToOne` cho phép nhiều entity nguồn cùng tham chiếu một entity đích; nếu nghiệp vụ chỉ cho phép một nguồn, cần ràng buộc duy nhất thích hợp.
- `@OneToOne` cần được bảo vệ bằng unique constraint ở database để tính duy nhất được bảo đảm kể cả khi có nhiều request đồng thời.

Nếu Article phải có từ một đến năm Tag, có thể biểu diễn ý định validation trên collection:

    @NotEmpty
    @Size(max = 5)
    @ManyToMany
    private Set<Tag> tags = new HashSet<>();

Đảm bảo validator được chạy sau các thao tác làm thay đổi association. Nếu endpoint association không kích hoạt đúng validation trên aggregate trong cấu hình hiện tại, hãy thực hiện kiểm tra ở service/domain boundary hoặc dùng repository event phù hợp. Không chỉ dựa vào validation phía trình duyệt.

Với quy tắc phức tạp hơn, chẳng hạn số tham chiếu phụ thuộc trạng thái đơn hàng hoặc loại khách hàng, nên dùng validator nghiệp vụ có ngữ cảnh. Ràng buộc database vẫn cần thiết cho tính duy nhất, khóa ngoại và NOT NULL; validation API không thay thế các ràng buộc đó.

## 6. Phân biệt lỗi số lượng và lỗi URI

Khi một request association thất bại, xác định chính xác loại lỗi trước khi sửa dữ liệu:

- **URI không tồn tại:** số tham chiếu có thể đúng, nhưng một URI không phân giải được đến entity đích.
- **Sai cardinality:** URI có thể đều tồn tại, nhưng client gửi nhiều URI cho thuộc tính đơn hoặc gửi body không đúng cấu trúc.
- **Vi phạm giới hạn nghiệp vụ:** số tham chiếu vượt giới hạn tối đa hoặc thấp hơn mức tối thiểu do domain quy định.
- **Vi phạm tính toàn vẹn:** tham chiếu tạo ra xung đột unique, foreign key hoặc NOT NULL ở database.

Ví dụ, Order có một customer bắt buộc và Article có tối đa năm tag:

- Order gửi một URI customer đang tồn tại: phù hợp cardinality.
- Order gửi hai URI customer: sai cardinality của thuộc tính đơn.
- Order gửi một URI customer không tồn tại: lỗi phân giải URI.
- Article gửi sáu URI tag hợp lệ: lỗi giới hạn nghiệp vụ, không phải lỗi URI.
- Article gửi URI tag thứ sáu nhưng tag không tồn tại: trước hết là lỗi phân giải tài nguyên đích.

Phân biệt các trường hợp này giúp client biết nên sửa payload, chọn tài nguyên đích hay thông báo người dùng về quy tắc nghiệp vụ.

## 7. Quy trình kiểm tra và xử lý

Khi triển khai hoặc debug association trong Spring Data REST, thực hiện theo thứ tự sau:

1. Gọi GET tài nguyên cha và đọc đúng liên kết association trong `_links`.
2. Gọi GET URI entity đích để xác nhận repository xuất bản endpoint và tài nguyên tồn tại.
3. Xác định thuộc tính là quan hệ đơn hay collection bằng mapping JPA.
4. Gửi request với method và media type phù hợp; dùng URI đầy đủ trong `text/uri-list`.
5. Kiểm tra validation cho quan hệ bắt buộc và giới hạn số lượng.
6. Đọc lại tài nguyên cha hoặc association sau khi cập nhật để xác nhận liên kết đã thay đổi.
7. Kiểm tra database khi lỗi liên quan NOT NULL, foreign key hoặc unique constraint.

Một bộ kiểm thử tích hợp tối thiểu nên có các trường hợp:

- Tạo entity mà thiếu quan hệ bắt buộc.
- Gán một URI entity đích tồn tại.
- Gán URI đúng cú pháp nhưng không có entity đích.
- Gửi nhiều URI cho một association đơn.
- Thêm và gỡ một phần tử trong collection association.
- Gửi collection có số phần tử dưới mức tối thiểu hoặc vượt mức tối đa.
- Gửi hai request cạnh tranh có thể vi phạm tính duy nhất.

Trong test, xác nhận cả HTTP status, response body và trạng thái quan hệ sau request. Nếu hệ thống tùy chỉnh exception handler, hãy khóa hợp đồng lỗi theo response thực tế của ứng dụng.

## 8. Nguyên tắc cần nhớ

Quan hệ bắt buộc phải được bảo vệ ở tầng validation, mapping JPA và database. URI tham chiếu phải trỏ đến tài nguyên thật, được xuất bản và có thể truy cập. Số lượng URI phải phù hợp cardinality; giới hạn tối thiểu/tối đa là quy tắc nghiệp vụ cần được khai báo và kiểm tra riêng.

Khi client dùng đúng association link từ HAL, gửi đúng URI list và server kiểm tra cả tính tồn tại lẫn số lượng tham chiếu, các lỗi liên kết trong Spring Data REST sẽ dễ phân loại và xử lý hơn.