# Descriptor, rel và các kiểu SEMANTIC, SAFE, IDEMPOTENT, UNSAFE

## Bối cảnh

Spring Data REST cung cấp REST API theo hướng hypermedia. Client không chỉ nhận dữ liệu mà còn có thể khám phá các liên kết và metadata do server công bố. Hai khái niệm quan trọng trong phần này là:

- **Descriptor**: mô tả ngữ nghĩa của dữ liệu hoặc một thao tác mà API hỗ trợ. Spring Data REST sử dụng định dạng ALPS để công bố profile metadata.
- **rel** (link relation): tên quan hệ của một hyperlink, cho biết link đang trỏ tới loại tài nguyên hoặc hành động nào. Trong HAL, rel là khóa nằm trong đối tượng `_links`.

Trong ALPS, descriptor có thể mang một trong bốn kiểu thường gặp: `SEMANTIC`, `SAFE`, `IDEMPOTENT` và `UNSAFE`. Các kiểu này mô tả ý nghĩa của dữ liệu hoặc đặc tính của một transition. Chúng không phải tên HTTP method và cũng không phải tên của link relation.

Để đọc metadata chính xác, cần tách biệt ba lớp: descriptor mô tả dữ liệu/thao tác; rel định danh quan hệ của link; URI trong `href` cho biết đích mà client có thể truy cập.

## 1. Descriptor là gì?

Descriptor là một phần tử metadata mô tả một khái niệm trong API. Trong ALPS (Application-Level Profile Semantics), descriptor có thể mô tả:

- Một thuộc tính dữ liệu, ví dụ `name`, `email`, `status`.
- Một representation hoặc nhóm thuộc tính.
- Một transition mà client có thể thực hiện, ví dụ đọc một người dùng, tạo mới hoặc cập nhật dữ liệu.
- Các thuộc tính đầu vào của một transition.

Một ALPS document có thể được trả về dưới dạng JSON với media type:

    application/alps+json

Ví dụ rút gọn:

    {
      "alps": {
        "version": "1.0",
        "descriptor": [
          {
            "id": "person-representation",
            "type": "SEMANTIC",
            "descriptor": [
              {
                "name": "firstName",
                "type": "SEMANTIC"
              },
              {
                "name": "email",
                "type": "SEMANTIC"
              }
            ]
          },
          {
            "id": "get-person",
            "name": "get-person",
            "type": "SAFE",
            "rt": "#person-representation"
          }
        ]
      }
    }

Đây là ví dụ minh họa cấu trúc và ý nghĩa của metadata; ID, tên và danh sách descriptor thực tế phụ thuộc repository cùng cấu hình của ứng dụng.

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `id` | Định danh descriptor trong profile; có thể được descriptor khác tham chiếu |
| `name` | Tên thuộc tính hoặc transition được mô tả |
| `type` | Phân loại descriptor: SEMANTIC, SAFE, IDEMPOTENT hoặc UNSAFE |
| `doc` | Tài liệu giải thích ý nghĩa của descriptor |
| `descriptor` | Danh sách descriptor con, thường dùng để mô tả các trường của representation hoặc input |
| `rt` | Tham chiếu tới descriptor mô tả kiểu representation trả về (return type) |
| `ext` | Metadata mở rộng được profile công bố |

Không phải descriptor nào cũng cần mọi trường trên. Ví dụ, descriptor mô tả một trường dữ liệu có thể chỉ cần `name` và `type`; descriptor mô tả transition có thể có thêm `id`, `rt` hoặc các descriptor con mô tả input.

### Phân biệt id và name

`id` và `name` có vai trò khác nhau:

- `id` dùng để định danh descriptor, đặc biệt khi descriptor khác cần tham chiếu tới nó.
- `name` mô tả tên của thuộc tính hoặc transition theo ngữ nghĩa của profile.

Ví dụ, một descriptor có `id="get-person"` và `name="get-person"` có thể trùng hai giá trị trong một trường hợp cụ thể, nhưng không nên mặc định hai trường luôn đồng nghĩa. Khi đọc `rt`, hãy xem đó là tham chiếu tới descriptor representation, không phải URL của endpoint.

## 2. ALPS profile trong Spring Data REST

Spring Data REST có thể công bố profile metadata để client hiểu các resource và thao tác mà API hỗ trợ. Resource thường cung cấp link relation `profile` trong HAL. Client theo link đó để lấy ALPS document.

Ví dụ request:

    GET http://localhost:8080/profile
    Accept: application/alps+json

Một response ALPS có thể mô tả representation của entity `Person`, các trường như `firstName` và `email`, cùng các transition liên quan đến repository.

Một descriptor representation có thể chứa các descriptor con:

    {
      "id": "person-representation",
      "type": "SEMANTIC",
      "descriptor": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "email",
          "type": "SEMANTIC"
        }
      ]
    }

Một descriptor transition có thể tham chiếu representation trả về:

    {
      "id": "get-person",
      "name": "get-person",
      "type": "SAFE",
      "rt": "#person-representation"
    }

Trong ví dụ này, descriptor đầu mô tả cấu trúc dữ liệu. Descriptor thứ hai mô tả một thao tác đọc và chỉ ra kiểu representation mà thao tác trả về. `rt` là tham chiếu trong profile; client không gọi `#person-representation` như một HTTP URL.

ALPS metadata giúp client khám phá ngữ nghĩa của API mà không phải suy đoán toàn bộ cấu trúc từ tên class Java hoặc tên cột database.

## 3. rel là gì?

`rel` là viết tắt của *link relation*. Nó mô tả mối quan hệ giữa tài nguyên hiện tại và tài nguyên được trỏ tới bởi hyperlink.

Trong HAL JSON, link relation thường xuất hiện như một khóa trong `_links`:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "orders": {
          "href": "http://localhost:8080/people/42/orders"
        }
      }
    }

Ở đây:

- `self` cho biết link trỏ tới chính resource hiện tại.
- `profile` cho biết link tới profile metadata.
- `orders` cho biết link tới resource liên quan là các đơn hàng của người dùng này.
- `href` là URI đích của từng link.

Rel trả lời câu hỏi “link này có ý nghĩa gì đối với resource hiện tại?”. Nó không mô tả HTTP method, không cho biết thao tác là safe hay unsafe và cũng không chứa nội dung của tài nguyên đích.

### Rel tiêu chuẩn và rel tùy chỉnh

Một số rel phổ biến được chuẩn hóa, ví dụ:

- `self`: chính tài nguyên hiện tại.
- `next`: tài nguyên/trang kế tiếp.
- `prev`: tài nguyên/trang trước.
- `first`: tài nguyên/trang đầu.
- `last`: tài nguyên/trang cuối.
- `profile`: profile mô tả tài nguyên.

API cũng có thể công bố rel riêng cho nghiệp vụ, chẳng hạn `orders`, `customer`, `search` hoặc một tên relation do ứng dụng chọn. Client nên dùng rel để tìm link có ý nghĩa cần thiết thay vì phân tích chuỗi URL.

## 4. Tùy chỉnh rel trong Spring Data REST

Spring Data REST cho phép tùy chỉnh tên collection relation, path và relation của finder hoặc association thông qua annotation.

Ví dụ tùy chỉnh collection relation:

    @RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
    )
    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

Collection resource có path `/people`; HAL có thể biểu diễn collection link với rel `people`.

Đối với finder method:

    @RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
    )
    public interface PersonRepository
            extends JpaRepository<Person, Long> {

        @RestResource(
            path = "by-email",
            rel = "by-email"
        )
        Optional<Person> findByEmail(String email);
    }

Finder được công bố dưới search resource; path `by-email` quyết định segment URL, còn rel `by-email` định danh link mà client tìm trong HAL.

Đối với association:

    @Entity
    public class PurchaseOrder {

        @ManyToOne
        @RestResource(
            path = "buyer",
            rel = "buyer"
        )
        private Customer customer;
    }

Association link có thể xuất hiện với rel `buyer` và URI tương ứng có path `buyer`.

Cần phân biệt:

| Thuộc tính | Tác dụng |
| --- | --- |
| `path` | Tùy chỉnh đường dẫn URI |
| `rel` | Tùy chỉnh tên quan hệ của link |
| `collectionResourceRel` | Tùy chỉnh rel của collection resource |
| `exported` | Điều khiển association hoặc resource có được xuất bản hay không |

Đổi `rel` không nhất thiết đổi URI. Đổi `path` không nhất thiết đổi tên rel. Nếu API đã có client sử dụng, hãy xem việc thay đổi hai giá trị này là thay đổi hợp đồng hypermedia và đánh giá ảnh hưởng tương thích.

## 5. Kiểu SEMANTIC

`SEMANTIC` mô tả dữ liệu hoặc ý nghĩa của một phần tử trong representation. Nó thường được dùng cho descriptor của thuộc tính entity hoặc descriptor đại diện cho cấu trúc dữ liệu.

Ví dụ:

    {
      "id": "person-representation",
      "type": "SEMANTIC",
      "descriptor": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "email",
          "type": "SEMANTIC"
        }
      ]
    }

Trong ví dụ này, `firstName` và `email` là các khái niệm dữ liệu của representation Person. Chúng không phải transition để client gọi.

Hãy nhớ:

- SEMANTIC mô tả “dữ liệu này có ý nghĩa gì?”.
- Nó không chỉ định GET, POST, PUT hay DELETE.
- Nó không khẳng định dữ liệu có thể được ghi hoặc chỉnh sửa.
- Quyền đọc/ghi vẫn do endpoint, mapping và Spring Security quyết định.

Một trường xuất hiện trong profile không đồng nghĩa client có thể gửi trường đó trong mọi request. Muốn biết input nào được chấp nhận, cần xem descriptor của transition tương ứng và hợp đồng của endpoint.

## 6. Kiểu SAFE

`SAFE` mô tả một transition không yêu cầu thay đổi trạng thái của tài nguyên trên server. Trong HTTP, GET là ví dụ điển hình của method safe.

Ví dụ descriptor:

    {
      "id": "get-person",
      "type": "SAFE",
      "rt": "#person-representation"
    }

Nó mô tả một thao tác đọc representation Person. Client có thể thực hiện transition này mà không yêu cầu server cập nhật dữ liệu nghiệp vụ.

Các đặc điểm:

- SAFE thường gắn với thao tác truy vấn/đọc.
- Một thao tác safe cũng có tính idempotent theo ngữ nghĩa HTTP.
- Safe không có nghĩa request không tạo bất kỳ log, metric hoặc cache entry nào; điều quan trọng là client không yêu cầu thay đổi trạng thái nghiệp vụ của tài nguyên.
- SAFE không phải cơ chế phân quyền. Người dùng vẫn có thể bị từ chối GET bởi Spring Security.

Ví dụ HTTP:

    GET /people/42
    Accept: application/hal+json

Request trên đọc resource Person 42. Nó không yêu cầu cập nhật Person.

## 7. Kiểu IDEMPOTENT

`IDEMPOTENT` mô tả transition có tính lặp an toàn về mặt hiệu ứng trạng thái: thực hiện một lần hay lặp lại nhiều lần với cùng request có cùng hiệu ứng cuối cùng đối với trạng thái được quản lý.

Điều này không có nghĩa request không làm thay đổi dữ liệu. Một thao tác có thể thay đổi trạng thái ở lần đầu, nhưng khi lặp lại thì không tạo thêm thay đổi khác.

Ví dụ phổ biến trong HTTP là PUT:

    PUT /people/42
    Content-Type: application/json

    {
      "firstName": "An",
      "email": "an@example.com"
    }

Nếu cùng representation được PUT nhiều lần tới cùng tài nguyên, trạng thái đích vẫn là nội dung được chỉ định. Do đó PUT có ngữ nghĩa idempotent theo HTTP.

DELETE cũng được định nghĩa là idempotent: mục tiêu là tài nguyên không còn tồn tại sau thao tác. Tuy nhiên, response HTTP của lần xóa đầu và lần xóa tiếp theo có thể khác nhau (ví dụ lần đầu 204, lần sau 404). Idempotence nói về hiệu ứng trạng thái dự kiến, không yêu cầu response phải giống hệt nhau.

Các điểm cần nhớ:

- IDEMPOTENT không đồng nghĩa SAFE.
- Một thao tác idempotent có thể thay đổi dữ liệu.
- PUT và DELETE là ví dụ điển hình của method idempotent nhưng không safe.
- Không nên đánh đồng idempotence với việc server không chạy lại code hoặc không ghi log.

## 8. Kiểu UNSAFE

`UNSAFE` mô tả transition có thể làm thay đổi trạng thái tài nguyên. Một thao tác unsafe có thể tạo mới, thay đổi hoặc kích hoạt xử lý nghiệp vụ.

Ví dụ phổ biến là POST tạo một resource:

    POST /people
    Content-Type: application/json

    {
      "firstName": "An",
      "email": "an@example.com"
    }

Nếu gửi cùng request nhiều lần, server có thể tạo nhiều bản ghi Person. Vì vậy POST thường không safe và cũng không idempotent theo ngữ nghĩa HTTP mặc định.

Các điểm cần nhớ:

- UNSAFE có thể làm thay đổi trạng thái server.
- Không nên tự động retry một request unsafe sau timeout nếu chưa biết request trước đã được xử lý hay chưa.
- Một API có thể thiết kế cơ chế idempotency key hoặc quy tắc nghiệp vụ riêng để kiểm soát request lặp, nhưng điều đó cần được mô tả rõ trong hợp đồng API.
- UNSAFE không đồng nghĩa request độc hại hoặc không được phép; nó chỉ mô tả khả năng thay đổi trạng thái.

Ví dụ khác là POST kích hoạt một nghiệp vụ như xác nhận đơn hàng. Dù endpoint không tạo bản ghi mới, nó vẫn có thể thay đổi trạng thái đơn hàng và do đó là transition unsafe.

## 9. So sánh bốn kiểu descriptor

| Kiểu | Ý nghĩa | Ví dụ điển hình | Có yêu cầu thay đổi trạng thái? |
| --- | --- | --- | --- |
| `SEMANTIC` | Mô tả dữ liệu hoặc khái niệm | `firstName`, `email` | Không phải transition; không áp dụng |
| `SAFE` | Transition chỉ đọc, không yêu cầu thay đổi trạng thái nghiệp vụ | GET | Không |
| `IDEMPOTENT` | Transition có cùng hiệu ứng trạng thái khi lặp cùng request | PUT, DELETE | Có thể có |
| `UNSAFE` | Transition có thể thay đổi trạng thái | POST tạo resource hoặc thực hiện nghiệp vụ | Có thể có |

Để nhớ nhanh:

- SEMANTIC nói về **ý nghĩa dữ liệu**.
- SAFE nói về **transition không yêu cầu thay đổi trạng thái**.
- IDEMPOTENT nói về **hiệu ứng trạng thái khi lặp request**.
- UNSAFE nói về **transition có thể làm thay đổi trạng thái**.

Đừng xem bốn kiểu này như bốn HTTP method. Chúng là metadata mô tả descriptor; HTTP method là một phần của giao thức request thực tế.

## 10. Quan hệ giữa SAFE, IDEMPOTENT và HTTP method

Theo ngữ nghĩa HTTP thông dụng:

| HTTP method | Safe | Idempotent | Ghi chú |
| --- | --- | --- | --- |
| GET | Có | Có | Đọc representation |
| HEAD | Có | Có | Đọc metadata của response |
| OPTIONS | Có | Có | Hỏi khả năng giao tiếp của resource |
| PUT | Không | Có | Đặt trạng thái tài nguyên theo nội dung request |
| DELETE | Không | Có | Yêu cầu xóa tài nguyên |
| POST | Không | Không theo mặc định | Thực hiện xử lý hoặc tạo resource |
| PATCH | Không | Không theo mặc định | Áp dụng thay đổi một phần |

Bảng trên mô tả ngữ nghĩa HTTP phổ biến. Một ứng dụng cụ thể có thể có hợp đồng nghiệp vụ chi tiết hơn, nhưng không nên tùy tiện thay đổi cách hiểu chuẩn của method.

SAFE là thuộc tính mạnh hơn về mặt tác động: một method safe cũng idempotent, nhưng một method idempotent chưa chắc safe. Ví dụ PUT có thể thay đổi trạng thái ở lần đầu nên không safe, dù việc gửi lại cùng nội dung vẫn hướng tới cùng trạng thái.

ALPS descriptor type là metadata để client hiểu transition. Đừng suy ra method chỉ từ một tên descriptor; hãy đọc link, URI, tài liệu và metadata của thao tác. Cũng đừng suy ra quyền truy cập từ SAFE hoặc IDEMPOTENT.

## 11. Đọc rel và descriptor cùng nhau

Hai loại metadata bổ sung cho nhau:

- HAL rel giúp client tìm link theo ý nghĩa của quan hệ.
- ALPS descriptor giúp client hiểu dữ liệu hoặc transition được mô tả trong profile.
- `href` cho biết URI cụ thể để client gửi request.
- HTTP method và representation/body xác định cách thực hiện request.

Ví dụ, một HAL response:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "orders": {
          "href": "http://localhost:8080/people/42/orders"
        }
      }
    }

Client có thể làm theo quy trình:

1. Tìm rel `profile` để lấy ALPS metadata.
2. Đọc các descriptor để hiểu representation và transition.
3. Tìm rel `orders` nếu cần điều hướng tới các đơn hàng.
4. Dùng URI trong `href` và method phù hợp để gọi API.

Một rel không tự mang type SAFE hoặc UNSAFE. Ví dụ rel `orders` chỉ nói link trỏ tới quan hệ đơn hàng. Muốn biết thao tác nào được hỗ trợ và tác động ra sao, cần xem profile hoặc hợp đồng endpoint tương ứng.

## 12. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| rel là HTTP method | rel định danh quan hệ của hyperlink; method nằm trong request |
| Descriptor là URL | Descriptor là metadata; `href` mới là URI để truy cập |
| SEMANTIC nghĩa là dữ liệu được phép ghi | SEMANTIC mô tả ý nghĩa dữ liệu, không cấp quyền ghi |
| SAFE và IDEMPOTENT giống nhau | SAFE là không yêu cầu thay đổi trạng thái; IDEMPOTENT là lặp request có cùng hiệu ứng trạng thái |
| IDEMPOTENT nghĩa là không thay đổi gì | PUT/DELETE có thể thay đổi trạng thái ở lần đầu |
| UNSAFE nghĩa là request nguy hiểm hoặc bị cấm | UNSAFE mô tả khả năng thay đổi trạng thái; quyền thực thi do API và security quyết định |
| Có rel là chắc chắn gọi được endpoint | Link có thể yêu cầu xác thực, quyền phù hợp hoặc điều kiện nghiệp vụ |
| Có descriptor là mọi client đều phải dùng nó | Descriptor cung cấp metadata; client vẫn phải tuân theo hợp đồng và khả năng thực tế của server |

## 13. Bài thực hành

Giả sử Spring Data REST xuất bản repository Person tại `/people`. Hãy thực hiện trong môi trường thử nghiệm:

1. Gọi `GET /people/42` với `Accept: application/hal+json`.
2. Đọc `_links` và phân biệt rel `self`, `profile` với các rel nghiệp vụ.
3. Theo link `profile` và yêu cầu `Accept: application/alps+json`.
4. Tìm descriptor representation của Person và các descriptor con như `firstName`, `email`.
5. Tìm descriptor transition đọc Person có type SAFE.
6. So sánh với descriptor mô tả thao tác tạo hoặc cập nhật, nếu profile công bố.
7. Thử PUT cùng một nội dung hai lần trong dữ liệu thử nghiệm và quan sát trạng thái cuối.
8. Thử POST tạo Person hai lần và quan sát liệu có tạo hai resource riêng hay không.
9. Kiểm tra cách Spring Security xử lý khi người dùng không có quyền truy cập.

Câu hỏi tự kiểm tra:

- Descriptor dùng để mô tả những loại thông tin nào?
- `id`, `name`, `type` và `rt` khác nhau như thế nào?
- Trong HAL, rel và href đảm nhiệm vai trò gì?
- Vì sao một descriptor SAFE cũng có ngữ nghĩa idempotent?
- Vì sao PUT có thể IDEMPOTENT nhưng không SAFE?
- Vì sao không nên tự động retry POST sau timeout?
- Metadata ALPS có thay thế authorization của Spring Security không?

## Tài liệu tham khảo

- [Spring Data REST Reference — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [ALPS Specification](https://alps.io/spec/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [HAL Specification](https://stateless.group/hal_specification.html)
