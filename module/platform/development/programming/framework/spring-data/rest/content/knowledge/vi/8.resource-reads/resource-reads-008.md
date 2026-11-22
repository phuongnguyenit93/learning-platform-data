# Thực hành lần theo liên kết từ tập hợp đến tài nguyên đơn

## 1. Mục tiêu bài thực hành

Trong Spring Data REST, một collection resource đại diện cho tập hợp entity của một repository, còn một item resource đại diện cho một entity cụ thể. Ví dụ, collection khách hàng có thể chứa nhiều khách hàng; mỗi khách hàng có một tài nguyên riêng để đọc hoặc cập nhật.

Bài thực hành này đi theo luồng hypermedia từ collection đến item:

1. Gửi request lấy collection resource.
2. Đọc các entity được nhúng trong phản hồi HAL.
3. Lấy liên kết self của entity cần mở.
4. Gửi request tới href của liên kết đó để lấy tài nguyên đơn.
5. Xử lý collection rỗng, item thiếu liên kết hoặc request thất bại.

Client lấy URL item từ phản hồi của server. Client không tự tạo URL bằng cách nối tên collection với ID, chẳng hạn /customers/42.

## 2. Chuẩn bị API mẫu

Giả sử ứng dụng Spring Data REST có repository:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Nếu repository được công bố với collection relation là customers, collection endpoint có thể được biểu diễn như sau:

    GET http://localhost:8080/customers
    Accept: application/hal+json

Đường dẫn /customers chỉ là ví dụ. Ứng dụng có thể cấu hình base path, path hoặc collectionResourceRel khác. Trong bài thực hành, hãy dùng URL collection mà API root hoặc cấu hình môi trường của ứng dụng cung cấp.

HAL là định dạng JSON biểu diễn tài nguyên và các liên kết hypermedia. Phản hồi collection thường có:

- **_embedded**: các entity được nhúng trong collection.
- **_links**: liên kết của collection, ví dụ self, profile hoặc liên kết phân trang.
- **page**: thông tin phân trang khi collection được phân trang.

Một phản hồi minh họa:

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
          },
          {
            "name": "Bình",
            "email": "binh@example.com",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/57"
              }
            }
          }
        ]
      },
      "page": {
        "size": 20,
        "totalElements": 2,
        "totalPages": 1,
        "number": 0
      }
    }

Trong ví dụ này, customers là collection relation. Mỗi phần tử trong mảng _embedded.customers là representation của một customer và có liên kết _links.self.href trỏ tới item resource tương ứng.

Tên relation trong _embedded phụ thuộc cấu hình API. Nếu ứng dụng đổi collectionResourceRel, key này cũng có thể thay đổi. Không nên mặc định mọi collection đều có key customers.

## 3. Bước 1 — Lấy collection resource

Có thể quan sát phản hồi bằng curl:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers

Header Accept yêu cầu server trả representation HAL JSON. Kiểm tra status code, Content-Type và phần body. Khi request thành công, body thường chứa _embedded cùng các link.

Nếu nhận 404 Not Found, hãy kiểm tra collection endpoint có đúng không và repository có được Spring Data REST công bố không. Nếu nhận 401 Unauthorized hoặc 403 Forbidden, cần xác thực hoặc quyền truy cập phù hợp. Những lỗi này không phải bằng chứng rằng cách lần theo link sai.

## 4. Bước 2 — Chọn một entity trong collection

Giả sử client cần mở customer đầu tiên. Trước tiên, lấy danh sách entity từ _embedded:

    const customers = collection._embedded?.customers ?? [];

    if (customers.length === 0) {
      console.log("Collection hiện không có customer nào.");
      return;
    }

    const selectedCustomer = customers[0];

Trong đoạn code trên, customers là tên collection relation của ví dụ. Với API khác, client phải dùng relation tương ứng trong response.

Không nên lấy ID từ trường dữ liệu rồi ghép URL:

    const customerUrl = "/customers/" + selectedCustomer.id;

Cách này phụ thuộc vào tên path và cách server biểu diễn ID. Một entity có thể dùng ID dạng UUID, slug hoặc định danh khác; server cũng có thể đổi URL mà không đổi ý nghĩa tài nguyên.

## 5. Bước 3 — Lấy liên kết self của item

Mỗi entity được nhúng thường có _links.self. Đây là liên kết tới representation độc lập của entity đó:

    const selfLink = selectedCustomer._links?.self;

    if (!selfLink?.href) {
      throw new Error("Entity không có liên kết self.");
    }

Giá trị href là URI do server cung cấp. Nó có thể là URL tuyệt đối hoặc URI tương đối. Khi cần, client có thể phân giải URI tương đối dựa trên URL của collection response:

    const itemUrl = new URL(selfLink.href, collectionUrl);

new URL(...) xử lý đúng việc kết hợp URI tương đối với URL gốc. Không nối chuỗi thủ công vì có thể tạo path sai khi URL chứa base path hoặc dấu gạch chéo.

self là relation thường dùng để chỉ tài nguyên hiện tại. Client có thể theo link này mà không cần biết server đã tạo item URL từ ID hay từ một quy tắc định tuyến khác.

## 6. Bước 4 — Gửi request lấy tài nguyên đơn

Sau khi có href, gửi request mới tới link đó:

    const itemResponse = await fetch(itemUrl, {
      headers: {
        Accept: "application/hal+json"
      }
    });

    if (!itemResponse.ok) {
      throw new Error(
        "Không thể tải customer: HTTP " + itemResponse.status
      );
    }

    const customerDetail = await itemResponse.json();

Tài nguyên đơn thường trả về các thuộc tính của entity và các link liên quan. Ví dụ:

    {
      "name": "An",
      "email": "an@example.com",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        },
        "orders": {
          "href": "http://localhost:8080/customers/42/orders"
        }
      }
    }

Client có thể tiếp tục điều hướng từ representation này. Nếu cần các đơn hàng, hãy đọc relation orders và theo href tương ứng khi link được công bố. Không cần tự suy ra endpoint association.

## 7. Ví dụ hoàn chỉnh bằng JavaScript fetch

Ví dụ sau ghép các bước thành một luồng duy nhất. Thay collectionUrl và collection relation bằng giá trị phù hợp với API của ứng dụng.

    async function loadFirstCustomer(collectionUrl) {
      const collectionResponse = await fetch(collectionUrl, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!collectionResponse.ok) {
        throw new Error(
          "Collection request failed: " + collectionResponse.status
        );
      }

      const collection = await collectionResponse.json();

      // Relation này là ví dụ; dùng key thực tế trong _embedded.
      const customers = collection._embedded?.customers ?? [];

      if (customers.length === 0) {
        return null;
      }

      const customer = customers[0];
      const selfHref = customer._links?.self?.href;

      if (!selfHref) {
        throw new Error("Customer representation has no self link");
      }

      // Hỗ trợ cả href tuyệt đối và tương đối.
      const itemUrl = new URL(selfHref, collectionResponse.url);

      const itemResponse = await fetch(itemUrl, {
        headers: {
          Accept: "application/hal+json"
        }
      });

      if (!itemResponse.ok) {
        throw new Error(
          "Item request failed: " + itemResponse.status
        );
      }

      return await itemResponse.json();
    }

    const customer = await loadFirstCustomer(
      "http://localhost:8080/customers"
    );

    console.log(customer);

Hàm trên trả về null khi collection rỗng; nếu collection có entity, nó trả về representation của item đầu tiên. Trong ứng dụng thật, URL collection nên được lấy từ entry point hoặc cấu hình môi trường, và tên relation nên được xác định từ hợp đồng API.

## 8. Phân biệt link self của collection và link self của item

Cả collection lẫn item đều có thể có relation self, nhưng hai link trỏ tới hai tài nguyên khác nhau:

| Vị trí | Link _links.self.href trỏ tới | Mục đích |
|---|---|---|
| Collection response | Chính collection | Tải lại tập hợp hiện tại |
| Entity trong _embedded | Tài nguyên đơn của entity | Đọc hoặc thao tác trên item |

Ví dụ:

- collection._links.self.href trỏ tới /customers.
- collection._embedded.customers[0]._links.self.href trỏ tới một item, ví dụ /customers/42.

Không lấy self ở cấp collection rồi dùng nó như URL của item. Hãy lấy link self nằm bên trong chính entity cần mở.

## 9. Collection phân trang và nhiều item

Khi collection có nhiều entity hơn kích thước trang, server có thể chỉ trả một phần dữ liệu. Client có thể duyệt các entity trong trang hiện tại và theo link next để lấy trang kế tiếp nếu link đó tồn tại.

Ví dụ:

    const nextHref = collection._links?.next?.href;

    if (nextHref) {
      const nextPageResponse = await fetch(
        new URL(nextHref, collectionResponse.url),
        {
          headers: {
            Accept: "application/hal+json"
          }
        }
      );

      if (!nextPageResponse.ok) {
        throw new Error("Không thể tải trang tiếp theo");
      }

      const nextPage = await nextPageResponse.json();
    }

Đối với từng item trong một trang, thực hiện cùng một quy trình: đọc item._links.self.href, phân giải URI và gửi request nếu client cần representation đầy đủ. Không phải lúc nào cũng cần tải lại item; collection response có thể đã chứa đủ trường mà giao diện cần. Chỉ gọi item endpoint khi cần dữ liệu chi tiết hoặc thao tác dành riêng cho tài nguyên đơn.

## 10. Lỗi thường gặp và cách xử lý

**Đọc nhầm link self**

Nếu lấy _links.self của collection, request tiếp theo chỉ tải lại collection. Hãy lấy _links.self trên entity bên trong _embedded.

**Entity không có link self**

Không tự ghép URL từ ID để thay thế. Kiểm tra response có đúng HAL không, entity có phải representation của Spring Data REST không và server có công bố link đó không. Nếu API không cung cấp link, xử lý như một trường hợp thiếu capability trong hợp đồng API.

**Dùng sai key trong _embedded**

Key như customers phụ thuộc collection relation. Đọc response thực tế hoặc dùng metadata/hợp đồng API để biết relation. Không giả định tên Java class luôn là key.

**Href tương đối**

Nếu href không phải URL tuyệt đối, phân giải nó dựa trên URL của response hiện tại bằng URL resolver. Không nối chuỗi path bằng tay.

**Request item bị từ chối**

401 thường liên quan đến xác thực; 403 liên quan đến quyền truy cập; 404 có thể nghĩa là tài nguyên không còn tồn tại hoặc route không hợp lệ. Hãy xử lý theo status code và chính sách bảo mật của ứng dụng.

**Dữ liệu collection đã cũ**

Một entity có thể bị xóa giữa lúc client tải collection và lúc client theo self link. Vì vậy, request item vẫn cần kiểm tra status code; không giả định item luôn tồn tại chỉ vì nó từng xuất hiện trong collection.

## 11. Bài tập thực hành

Dùng một ứng dụng Spring Data REST có ít nhất hai customer:

1. Gửi GET đến collection endpoint với Accept: application/hal+json.
2. Tìm _embedded và xác định key chứa các customer.
3. Chọn entity thứ hai trong collection.
4. Đọc _links.self.href của entity đó.
5. Gửi GET tới href vừa đọc và kiểm tra response là tài nguyên đơn.
6. So sánh self ở cấp collection với self ở cấp entity.
7. Thử với collection rỗng hoặc một entity đã bị xóa để quan sát cách client xử lý.

Câu hỏi tự kiểm tra:

- Vì sao client không nên tạo item URL bằng cách ghép ID?
- Link self nào trỏ tới collection, link nào trỏ tới item?
- Nếu href tương đối, client cần phân giải nó dựa trên URL nào?
- Khi entity xuất hiện trong collection nhưng bị xóa trước request tiếp theo, client nên xử lý thế nào?

## 12. Ghi nhớ

- Collection resource biểu diễn tập hợp; item resource biểu diễn một entity cụ thể.
- Entity trong _embedded có thể cung cấp link self trỏ tới tài nguyên đơn.
- Lấy self link từ chính entity cần mở, không lấy self link của collection.
- Dùng href server trả về; không ghép cứng URL từ ID hoặc tên repository.
- Phân giải href tương đối dựa trên URL của response.
- Kiểm tra status code và xử lý collection rỗng, link thiếu, item bị xóa hoặc request bị từ chối.
- Chỉ tải item riêng khi cần representation hoặc thao tác chi tiết.

## Tài liệu tham khảo

- Spring Data REST Reference: https://docs.spring.io/spring-data/rest/reference/
- Spring HATEOAS Reference: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- HAL specification: https://stateless.group/hal_specification.html
