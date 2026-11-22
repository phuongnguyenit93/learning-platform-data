# Khám phá tài nguyên từ API gốc thay vì ghép cứng URL

## 1. Vì sao client nên bắt đầu từ API gốc?

Khi xây dựng client cho Spring Data REST, ta thường biết URL gốc của dịch vụ, ví dụ `http://localhost:8080/`. Tuy nhiên, không nên tự suy ra các endpoint còn lại bằng cách ghép chuỗi như `/customers`, `/customers/42` hoặc `/customers/search/findByEmail`.

Đường dẫn là chi tiết triển khai của API. Chúng có thể thay đổi khi server cấu hình `path`, `collectionResourceRel`, đổi tên repository, thay đổi cấu trúc tài nguyên hoặc chuyển dịch vụ sang một phiên bản khác. Nếu client tự ghép URL, mỗi thay đổi đó có thể buộc client phải sửa và phát hành lại.

Spring Data REST dùng hypermedia để công bố các liên kết mà client có thể đi theo. Client lấy API root, đọc các link do server trả về, chọn link theo quan hệ (relation, thường gọi là `rel`) và tiếp tục khám phá tài nguyên. Cách này tuân theo nguyên tắc HATEOAS: phản hồi của API cung cấp thông tin cần thiết để client điều hướng trạng thái tiếp theo.

Client vẫn cần biết API root và ý nghĩa nghiệp vụ của thao tác mình muốn thực hiện. Sau điểm bắt đầu đó, client nên dùng các quan hệ và URL do server cung cấp thay vì tự đoán cấu trúc đường dẫn.

## 2. HAL và HATEOAS trong Spring Data REST

**HATEOAS** (Hypertext as the Engine of Application State) là nguyên tắc thiết kế trong đó tài nguyên trả về các liên kết mô tả những bước tiếp theo mà client có thể thực hiện. Client điều hướng thông qua các liên kết này thay vì phụ thuộc vào một sơ đồ URL cố định.

**HAL** (Hypertext Application Language) là định dạng JSON phổ biến để biểu diễn tài nguyên và liên kết hypermedia. Spring Data REST thường trả về HAL JSON với media type:

    application/hal+json

Một tài liệu HAL thường có hai phần đáng chú ý:

- `_links`: các liên kết đến tài nguyên liên quan, được nhóm theo link relation.
- `_embedded`: các tài nguyên được nhúng trong phản hồi, thường xuất hiện trong collection resource.

Ví dụ minh họa phản hồi tại API root:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "customers": {
          "href": "http://localhost:8080/customers"
        }
      }
    }

Trong ví dụ này, `customers` là quan hệ dẫn tới collection resource khách hàng. Đây chỉ là ví dụ minh họa: rel thực tế phụ thuộc cấu hình và metadata của ứng dụng. Client phải đọc key và `href` trong phản hồi thực tế, không được giả định mọi ứng dụng đều dùng tên `customers`.

Một link có thể chứa thêm thuộc tính như `templated`, `type`, `title` hoặc `deprecation`. Client nên dựa vào định dạng HAL và thư viện hypermedia để xử lý các thuộc tính đó, thay vì chỉ coi mọi giá trị link là một chuỗi URL đơn giản.

## 3. Khám phá collection từ API root

Luồng cơ bản gồm các bước:

1. Gửi request đến API root đã được cấu hình.
2. Yêu cầu HAL JSON bằng header `Accept: application/hal+json`.
3. Đọc object `_links` trong phản hồi.
4. Tìm link theo rel mà client cần, ví dụ rel đại diện cho collection khách hàng.
5. Gửi request đến giá trị `href` của link đó.

Ví dụ dùng JavaScript `fetch` trong trình duyệt hoặc môi trường Node có hỗ trợ fetch:

    const rootResponse = await fetch("http://localhost:8080/", {
      headers: { Accept: "application/hal+json" }
    });

    if (!rootResponse.ok) {
      throw new Error("Không thể tải API root: " + rootResponse.status);
    }

    const root = await rootResponse.json();

    // "customers" chỉ là rel minh họa; hãy dùng rel thực tế server trả về.
    const customersLink = root._links.customers;

    if (!customersLink) {
      throw new Error("API root không công bố rel customers");
    }

    const customersResponse = await fetch(customersLink.href, {
      headers: { Accept: "application/hal+json" }
    });

    if (!customersResponse.ok) {
      throw new Error("Không thể tải collection khách hàng");
    }

    const customersPage = await customersResponse.json();

Đoạn code chỉ cấu hình cứng URL API root. Collection URL được lấy từ `href` của link server trả về. Trong ứng dụng thực tế, rel cần dùng phải được xác định theo hợp đồng hypermedia của API; nếu server đổi path nhưng giữ rel, client vẫn có thể đi theo link mới.

Không nên viết:

    const customers = await fetch("http://localhost:8080/customers");
    const customer = await fetch("http://localhost:8080/customers/42");

Hai URL trên buộc client phải biết trước cấu trúc đường dẫn và cách server tạo định danh tài nguyên.

## 4. Đi theo link đến một tài nguyên cụ thể

Một collection response HAL thường có `_embedded` chứa các item, cùng các link của collection. Ví dụ:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        },
        "profile": {
          "href": "http://localhost:8080/profile/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "name": "An",
            "email": "an@example.com",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/42"
              }
            }
          }
        ]
      },
      "page": {
        "size": 20,
        "totalElements": 1,
        "totalPages": 1,
        "number": 0
      }
    }

Nếu client muốn mở chi tiết khách hàng đầu tiên, hãy lấy link `self` của item:

    const customer = customersPage._embedded.customers[0];
    const customerSelfLink = customer._links.self;

    const detailResponse = await fetch(customerSelfLink.href, {
      headers: { Accept: "application/hal+json" }
    });

    const customerDetail = await detailResponse.json();

Trong ví dụ này, client không tự ghép `/customers/42`. Server có quyền thay đổi URL item; client tiếp tục hoạt động nếu server cung cấp link `self` hợp lệ.

`_embedded` và tên collection bên trong nó cũng cần được đọc theo response thực tế. Không nên mặc định mọi collection đều có tên `_embedded.customers` nếu rel của ứng dụng được cấu hình khác.

## 5. Khám phá chức năng tìm kiếm qua rel `search`

Spring Data REST có thể công bố các query method của repository dưới một search resource. Thay vì tự đoán URL của finder, client nên:

1. Đọc link `search` từ collection response.
2. Đi theo link đó để lấy danh sách các finder được công bố.
3. Chọn finder bằng rel của nó.
4. Dùng URL template mà server cung cấp để truyền tham số.

Ví dụ, search resource có thể trả về:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/search"
        },
        "findByEmail": {
          "href": "http://localhost:8080/customers/search/findByEmail{?email}",
          "templated": true
        }
      }
    }

Thuộc tính `templated: true` cho biết `href` là URI template. Phần `{?email}` mô tả query parameter có thể được mở rộng. Client phải dùng URI-template expander hoặc thư viện hypermedia để thay tham số đúng cách, bao gồm mã hóa ký tự trong giá trị.

Ví dụ, với Spring HATEOAS `Traverson`, client có thể điều hướng theo chuỗi rel và truyền tham số cho template:

    Traverson traverson = new Traverson(
        URI.create("http://localhost:8080/"),
        MediaTypes.HAL_JSON
    );

    CollectionModel<EntityModel<Customer>> result =
        traverson.follow("customers", "search", "findByEmail")
            .withParameter("email", "an@example.com")
            .toObject(new ParameterizedTypeReference<>() {});

Các rel `customers`, `search` và `findByEmail` trong đoạn code là ví dụ. Hãy dùng đúng rel xuất hiện trong HAL response của ứng dụng. Kiểu dữ liệu nhận về cũng cần khớp với kiểu kết quả finder thực tế; finder trả một item và finder trả collection có kiểu phản hồi khác nhau.

Không nên ghép URL như sau:

    const url =
      "http://localhost:8080/customers/search/findByEmail?email=" +
      email;

Cách làm này giả định path, tên finder và tên tham số luôn cố định. Nó cũng dễ tạo URL sai nếu giá trị chứa dấu `&`, dấu `?` hoặc ký tự Unicode.

## 6. Theo link phân trang và liên kết quan hệ

Collection lớn thường được trả về theo từng trang. HAL response có thể chứa metadata phân trang trong `page` và các link điều hướng như `first`, `prev`, `self`, `next` hoặc `last`, tùy response và cấu hình.

Client nên đi theo link `next` nếu link đó được cung cấp:

    const nextLink = customersPage._links.next;

    if (nextLink) {
      const nextResponse = await fetch(nextLink.href, {
        headers: { Accept: "application/hal+json" }
      });
      const nextPage = await nextResponse.json();
    }

Nếu không có link `next`, client không nên tự giả định trang tiếp theo tồn tại. Metadata `page` có thể giúp hiển thị thông tin số trang, nhưng link điều hướng từ server mới là chỉ dẫn để đi tiếp.

Item resource cũng có thể chứa link tới tài nguyên liên quan, ví dụ địa chỉ, đơn hàng hoặc một association. Client có thể dùng rel đó để đi tiếp mà không cần biết association được ánh xạ thành đường dẫn nào.

## 7. Link relation quan trọng và cách hiểu

| Relation hoặc thuộc tính | Ý nghĩa thường gặp |
|---|---|
| `self` | Link tới chính tài nguyên hiện tại |
| `profile` | Link tới mô tả profile của tài nguyên |
| `search` | Link tới search resource của collection |
| `next` / `prev` | Điều hướng trang kế tiếp hoặc trước đó khi được cung cấp |
| `_embedded` | Các tài nguyên được nhúng trong representation |
| `href` | Địa chỉ của link |
| `templated` | Cho biết href là URI template cần mở rộng |

Rel là tên định danh cho mối quan hệ giữa tài nguyên hiện tại và tài nguyên đích. Một số rel là quan hệ chuẩn; một số khác do ứng dụng công bố. Không nên coi tên rel là path. `customers` có thể là key của một link, còn `href` mới chứa URI cụ thể để client truy cập.

Tên rel và cấu trúc response phụ thuộc server. Ví dụ, `@RepositoryRestResource(collectionResourceRel = "people")` có thể làm rel của collection khác tên mặc định. Đây là một lý do quan trọng để client khám phá link từ API root thay vì ghép cứng URL.

## 8. Thiết kế client bền vững

Một client HATEOAS tốt thường tuân theo các nguyên tắc sau:

- Chỉ cấu hình API root hoặc địa chỉ entry point theo môi trường.
- Yêu cầu đúng media type hypermedia mà API hỗ trợ, ví dụ `application/hal+json`.
- Chọn link bằng rel có ý nghĩa, rồi truy cập `href` do server cung cấp.
- Dùng URI-template expander cho link có `templated: true`; không tự thay chuỗi thủ công.
- Theo link `self` để mở item và theo link phân trang nếu được cung cấp.
- Xử lý trường hợp link không tồn tại, response lỗi, hoặc media type không đúng.
- Không giả định mọi link luôn xuất hiện trong mọi trạng thái của tài nguyên.
- Không phụ thuộc vào thứ tự key trong JSON hoặc vị trí của link trong mảng.

Việc dùng rel không có nghĩa client không cần hiểu nghiệp vụ. Client vẫn cần biết thao tác nào phù hợp với tác vụ của người dùng và rel nào trong hợp đồng API đại diện cho thao tác đó. Hypermedia giúp client tìm địa chỉ và bước tiếp theo do server công bố.

API root là entry point đã biết trước; các tài nguyên còn lại được khám phá dần từ phản hồi. Nếu server thay đổi đường dẫn collection nhưng vẫn cung cấp cùng rel, client có thể tiếp tục hoạt động mà không phải cập nhật URL đã ghép cứng.

## 9. Các lỗi thường gặp

**Tự ghép path từ tên entity hoặc repository**

Client giả định tên class `Customer` luôn tương ứng với `/customers`. Nhưng `path` và `collectionResourceRel` có thể được cấu hình khác. Hãy dùng rel và href từ response.

**Dùng link template như URL hoàn chỉnh**

Một link có `templated: true` chứa placeholder. Gửi request trực tiếp với placeholder chưa được mở rộng có thể dẫn đến URL không hợp lệ. Hãy mở rộng template bằng thư viện tương thích.

**Đọc sai vị trí dữ liệu**

Collection items thường nằm trong `_embedded`; link điều hướng nằm trong `_links`. Không nên giả định các item luôn nằm ở một thuộc tính cố định ngoài HAL.

**Giả định mọi rel đều có mặt**

Một repository có thể không công bố search resource, một collection có thể không có trang kế tiếp, hoặc một association có thể không được expose. Client phải xử lý trường hợp thiếu link như một trạng thái bình thường.

**Nhầm profile với endpoint nghiệp vụ**

Link `profile` mô tả profile của tài nguyên; nó không nhất thiết là endpoint để đọc hoặc cập nhật một entity.

**Chỉ kiểm tra bằng URL trên trình duyệt**

Mở được một URL không chứng minh client đã khám phá đúng quan hệ. Hãy kiểm tra response HAL, media type, rel và link template để hiểu cách API hướng dẫn client.

## 10. Thực hành với Spring Data REST

Giả sử ứng dụng công bố một `CustomerRepository` và API root là `http://localhost:8080/`.

1. Gửi `GET /` với `Accept: application/hal+json`.
2. Ghi lại các rel trong `_links` và xác định rel collection khách hàng.
3. Theo href của rel collection để lấy HAL collection response.
4. Tìm một item trong `_embedded`, sau đó theo link `self` của item.
5. Tìm link `search` nếu collection công bố search.
6. Theo một finder link; nếu link có `templated: true`, mở rộng template với tham số hợp lệ.
7. Nếu response có `next`, theo link đó để lấy trang tiếp theo.

Có thể dùng `curl` để quan sát HAL response:

    curl -i -H "Accept: application/hal+json" http://localhost:8080/

Sau đó kiểm tra href được trả về để hiểu bước tiếp theo. Trong client thực tế, việc điều hướng phải được thực hiện bằng code đọc rel và href, không dựa trên thao tác sao chép URL thủ công.

## 11. Ghi nhớ

- HATEOAS cho phép client điều hướng trạng thái ứng dụng thông qua các liên kết do server cung cấp.
- HAL biểu diễn link trong `_links` và tài nguyên nhúng trong `_embedded`.
- API root là entry point; client khám phá collection, item, search và các tài nguyên liên quan từ response.
- Dùng rel để tìm loại quan hệ cần thiết và dùng href server trả về để gửi request.
- Link có `templated: true` phải được mở rộng đúng cách.
- Theo link phân trang và association nếu response công bố chúng.
- Không ghép cứng URL cho các tài nguyên phía sau API root.

## Tài liệu tham khảo

- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring HATEOAS Reference — Traverson client: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- HAL specification: https://stateless.group/hal_specification.html
