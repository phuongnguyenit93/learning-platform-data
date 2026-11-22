# Biểu diễn tài nguyên đơn, tập hợp và kết quả phân trang trong Spring Data REST

## Mục tiêu

Spring Data REST biến các Spring Data Repository được export thành REST resource và biểu diễn chúng bằng hypermedia. Khi đọc API, cần nhận ra ba dạng response thường gặp:

- **Tài nguyên đơn (item resource):** biểu diễn một entity, thường được truy cập qua URI định danh như \`/people/42\`.
- **Tài nguyên tập hợp (collection resource):** biểu diễn danh sách entity thuộc một repository, thường ở URI như \`/people\`.
- **Tập hợp có phân trang (paged collection):** biểu diễn một trang của collection, kèm metadata về trang hiện tại và các liên kết điều hướng.

Các response này không chỉ chứa dữ liệu domain. Chúng còn chứa liên kết mô tả tài nguyên hiện tại, quan hệ tới tài nguyên liên quan và các bước mà client có thể thực hiện tiếp theo. Đó là phần hypermedia trong HATEOAS.

Bài này tập trung vào cấu trúc HAL mà Spring Data REST thường trả về, ý nghĩa của \`_links\`, \`_embedded\`, \`page\`, cách đọc các liên kết phân trang và cách client nên điều hướng API.

## 1. Từ repository đến REST resource

Giả sử ứng dụng export repository:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Với base path \`/api\`, Spring Data REST cung cấp các resource có dạng:

| URI | Ý nghĩa |
|---|---|
| \`GET /api/people\` | Collection resource của repository Person. |
| \`GET /api/people/42\` | Item resource của Person có identifier 42. |
| \`GET /api/people/42/manager\` | Resource biểu diễn association manager của Person 42, nếu association được export. |
| \`GET /api/people/search\` | Search resource chứa các query method được export, nếu có. |

Các URL là ví dụ minh họa. URI thực tế phụ thuộc base path, \`@RepositoryRestResource\`, cấu hình export và metadata repository.

Một request tới item resource và một request tới collection resource có mục đích khác nhau. Item resource mô tả một entity cụ thể. Collection resource mô tả tập hợp các entity và cung cấp các liên kết để client mở từng item hoặc đi tới trang khác.

## 2. HAL và cấu trúc hypermedia

Spring Data REST thường sử dụng HAL (Hypertext Application Language) làm định dạng hypermedia cho JSON response. Client có thể yêu cầu media type:

~~~http
Accept: application/hal+json
~~~

HAL quy ước một số trường đặc biệt:

| Trường | Ý nghĩa |
|---|---|
| \`_links\` | Các liên kết tới resource hiện tại, resource liên quan hoặc hành động điều hướng. |
| \`_embedded\` | Các resource được nhúng trong representation hiện tại, thường dùng cho các item của collection. |
| \`page\` | Metadata phân trang do Spring Data REST thêm vào representation của collection có phân trang. |
| Các thuộc tính domain | Dữ liệu của entity, ví dụ \`id\`, \`firstName\`, \`lastName\`. |

Một HAL link thường có dạng:

~~~json
{
  "self": {
    "href": "http://localhost:8080/api/people/42"
  }
}
~~~

Trong đó:

- **Relation (rel)** là tên quan hệ, ở ví dụ là \`self\`.
- **href** là URI mà client có thể gọi.
- **templated** có thể xuất hiện với giá trị \`true\` nếu URI là URI template còn chứa biến cần thay thế.

Tên relation cho client biết liên kết đại diện cho điều gì. Client nên dựa vào relation và href do server trả về, thay vì tự ghép URL theo quy tắc đặt tên mà nó đoán được.

HAL không bắt buộc mọi thuộc tính domain phải nằm trong \`_embedded\`. Dữ liệu của item thường nằm trực tiếp ở cấp ngoài của object; \`_embedded\` dùng để chứa các resource con được nhúng.

## 3. Biểu diễn một tài nguyên đơn

Khi client gọi:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Spring Data REST có thể trả về representation như sau:

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "lastName": "Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    },
    "addresses": {
      "href": "http://localhost:8080/api/people/42/addresses"
    }
  }
}
~~~

Đây là ví dụ rút gọn. Các thuộc tính và association link cụ thể phụ thuộc entity model, repository metadata và cấu hình export.

### Cách đọc response

- \`id\`, \`firstName\`, \`lastName\` là dữ liệu domain của Person.
- \`_links.self.href\` trỏ về chính item resource hiện tại.
- \`_links.addresses.href\` trỏ tới resource association addresses của Person này, nếu association được export.
- Một link association cho phép client truy cập tài nguyên liên quan mà không cần biết trước cấu trúc lưu trữ hoặc cách tạo URI.

Item resource không cần một mảng \`_embedded\` chỉ để biểu diễn chính entity đó. Nó là một object đơn có thuộc tính domain và các link liên quan.

### Vì sao cần link self?

Link \`self\` cho client URI chuẩn của resource. Client có thể lưu URI này, gọi lại để lấy dữ liệu mới nhất hoặc dùng nó làm tham chiếu trong thao tác tiếp theo. Điều này cũng giúp server thay đổi base path hay quy tắc URI mà client ít phải thay đổi, miễn là client tuân theo các liên kết được cung cấp.

### Association được biểu diễn thế nào?

Giả sử Person có association tới manager. Representation có thể chứa một link như:

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    },
    "manager": {
      "href": "http://localhost:8080/api/people/42/manager"
    }
  }
}
~~~

Client theo link \`manager\` để đọc association. Tùy cấu hình và kiểu association, response của endpoint liên quan có thể là một item resource hoặc một collection resource.

Mặc định, link association không đồng nghĩa toàn bộ object liên quan luôn được nhúng vào response của item. Đây là cách giữ representation gọn và giúp client chỉ tải tài nguyên liên quan khi cần.

## 4. Biểu diễn một collection resource

Khi client gọi:

~~~http
GET /api/people
Accept: application/hal+json
~~~

Spring Data REST trả về một collection representation. Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/api/people/search"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "firstName": "Ada",
        "lastName": "Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      },
      {
        "id": 43,
        "firstName": "Grace",
        "lastName": "Hopper",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/43"
          }
        }
      }
    ]
  }
}
~~~

### Hai tầng liên kết

Collection representation có hai tầng link:

1. **Các link ở cấp collection:** nằm trong \`_links\` bên ngoài. Chúng mô tả collection hiện tại, profile hoặc search endpoint.
2. **Các link ở cấp từng item:** nằm trong \`_links\` của từng object trong mảng \`_embedded.people\`. Chúng cho phép mở từng Person cụ thể.

Tên \`people\` trong \`_embedded\` là collection relation. Nó thường được suy ra từ tên domain/repository, và có thể được tùy chỉnh bằng \`collectionResourceRel\` trên \`@RepositoryRestResource\`.

### Ý nghĩa các relation thường gặp

| Relation | Ý nghĩa |
|---|---|
| \`self\` | URI của collection hiện tại. |
| \`profile\` | Liên kết tới mô tả profile/metadata của resource, thường dùng để khám phá ngữ nghĩa và cấu trúc. |
| \`search\` | Liên kết tới search resource của repository khi có query method được export. |
| \`people\` | Relation trong \`_embedded\` chứa các item thuộc collection People. |

Không nên giả định mọi collection đều có đầy đủ \`profile\` và \`search\`. Sự hiện diện của link phụ thuộc cấu hình, repository và các search method được export.

### Collection rỗng

Nếu không có entity nào phù hợp, collection vẫn là resource hợp lệ. Client phải chấp nhận collection rỗng: mảng trong \`_embedded\` có thể rỗng hoặc phần \`_embedded\` có thể không xuất hiện tùy representation và phiên bản. Đừng coi việc thiếu item là lỗi parse response.

## 5. Biểu diễn collection có phân trang

Với repository lớn, Spring Data REST thường trả collection theo từng trang. Client có thể chỉ định trang và kích thước trang:

~~~http
GET /api/people?page=0&size=2&sort=lastName,asc
Accept: application/hal+json
~~~

Một response minh họa:

~~~json
{
  "_links": {
    "first": {
      "href": "http://localhost:8080/api/people?page=0&size=2&sort=lastName,asc"
    },
    "self": {
      "href": "http://localhost:8080/api/people?page=0&size=2&sort=lastName,asc"
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=2&sort=lastName,asc"
    },
    "last": {
      "href": "http://localhost:8080/api/people?page=2&size=2&sort=lastName,asc"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "firstName": "Ada",
        "lastName": "Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      },
      {
        "id": 43,
        "firstName": "Grace",
        "lastName": "Hopper",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/43"
          }
        }
      }
    ]
  },
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Đây là response minh họa cho trang đầu của một collection có 5 phần tử, với page size bằng 2. Các link và item cụ thể được server tạo dựa trên dữ liệu thực tế.

### Metadata trong page

| Trường | Ý nghĩa |
|---|---|
| \`size\` | Kích thước trang hiện tại được áp dụng. |
| \`totalElements\` | Tổng số phần tử trong collection theo điều kiện truy vấn hiện tại. |
| \`totalPages\` | Tổng số trang có thể có. |
| \`number\` | Chỉ số trang hiện tại, mặc định bắt đầu từ 0. |

Ví dụ trên có:

- \`size = 2\`: mỗi trang chứa tối đa hai item.
- \`totalElements = 5\`: toàn bộ kết quả có năm item.
- \`totalPages = 3\`: cần ba trang để đọc hết kết quả.
- \`number = 0\`: đây là trang đầu tiên.

Metadata \`page\` mô tả trạng thái phân trang của collection response. Nó không phải một thuộc tính của entity Person và cũng không xuất hiện như metadata của một item resource đơn.

### Các link điều hướng

| Relation | Vai trò |
|---|---|
| \`first\` | Trang đầu tiên. |
| \`prev\` | Trang ngay trước trang hiện tại. |
| \`self\` | Trang hiện tại. |
| \`next\` | Trang kế tiếp. |
| \`last\` | Trang cuối cùng. |

Các link điều hướng chỉ xuất hiện khi phù hợp với vị trí trang và trạng thái kết quả. Ví dụ, trang đầu thường không có \`prev\`; trang cuối thường không có \`next\`. Collection chỉ có một trang có thể không cần link \`next\` hoặc \`last\`.

Client nên theo link \`next\` được trả về để chuyển trang. Không nên tự tăng số trang rồi dựng URI nếu server đã cung cấp liên kết điều hướng.

## 6. Query parameter cho phân trang và sorting

Spring Data REST hỗ trợ các query parameter phổ biến:

| Parameter | Ví dụ | Ý nghĩa |
|---|---|---|
| \`page\` | \`page=0\` | Chỉ số trang cần đọc, mặc định thường là 0. |
| \`size\` | \`size=20\` | Số item tối đa trong một trang. |
| \`sort\` | \`sort=lastName,asc\` | Sắp xếp theo thuộc tính và chiều tăng/giảm. |

Ví dụ:

~~~http
GET /api/people?page=1&size=10&sort=lastName,asc
~~~

Request này yêu cầu trang thứ hai (chỉ số 1), tối đa 10 item, sắp xếp theo \`lastName\` tăng dần.

Có thể yêu cầu nhiều tiêu chí sắp xếp bằng cách lặp query parameter:

~~~http
GET /api/people?sort=lastName,asc&sort=firstName,desc
~~~

Server áp dụng thứ tự sort theo các tiêu chí được yêu cầu và khả năng hỗ trợ của repository/store module.

### Giới hạn page size

Server có thể áp dụng page size mặc định và giới hạn tối đa để tránh một request tải quá nhiều dữ liệu. Trong Spring Boot có thể cấu hình:

~~~properties
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
~~~

Các giá trị trên là cấu hình ví dụ. Hãy đặt giới hạn theo dung lượng response, hiệu năng truy vấn và nhu cầu của client. Nếu client yêu cầu \`size\` lớn hơn giới hạn, server có thể giới hạn kích thước thực tế; hãy đọc metadata và link được trả về để biết trạng thái trang đang dùng.

Tên parameter mặc định có thể được tùy chỉnh trong \`RepositoryRestConfiguration\`. Khi dự án thay đổi tên \`page\`, \`size\` hoặc \`sort\`, client phải dùng tên mà API thực tế công bố.

## 7. Phân biệt item, collection và page

| Đặc điểm | Item resource | Collection resource | Paged collection |
|---|---|---|---|
| Mục đích | Một entity cụ thể. | Tập hợp entity. | Một phần của collection theo trang. |
| URI ví dụ | \`/api/people/42\` | \`/api/people\` | \`/api/people?page=1&size=10\` |
| Dữ liệu domain | Thuộc tính của một entity. | Các item trong \`_embedded\`. | Các item của trang hiện tại trong \`_embedded\`. |
| \`_links\` | Self và association links. | Link của collection, profile, search. | Link collection và link điều hướng trang. |
| \`_embedded\` | Có thể có nếu representation nhúng resource liên quan; không phải wrapper bắt buộc cho chính item. | Chứa các item của collection. | Chứa các item thuộc trang hiện tại. |
| \`page\` | Không dùng để mô tả item đơn. | Có thể không xuất hiện nếu không có phân trang. | Chứa page size, tổng item, tổng trang và chỉ số trang. |

Một cách nhận diện nhanh:

- Nếu response chứa trực tiếp các thuộc tính của một entity và có \`_links.self\`, đó thường là item resource.
- Nếu response có \`_embedded\` với một relation như \`people\`, đó là collection representation.
- Nếu collection response có thêm object \`page\` và các link như \`next\`, \`prev\`, đó là paged collection.

## 8. Tùy chỉnh relation và đường dẫn resource

Tên collection relation và URI có thể tùy chỉnh qua \`@RepositoryRestResource\`:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Hai thuộc tính có vai trò khác nhau:

- \`path\` quyết định segment URL của collection resource.
- \`collectionResourceRel\` quyết định tên relation được dùng để nhúng các item trong \`_embedded\`.

Ví dụ, nếu thay \`collectionResourceRel\` thành \`members\`, client có thể thấy:

~~~json
{
  "_embedded": {
    "members": [
      {
        "id": 42,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      }
    ]
  }
}
~~~

URI vẫn có thể là \`/api/people\`, trong khi tên relation là \`members\`. Client không nên suy ra relation từ URL hoặc tên Java interface.

Với association hoặc query method, \`@RestResource\` có thể tùy chỉnh rel và path tương ứng:

~~~java
@RestResource(rel = "manager", path = "manager")
Person getManager();
~~~

Đây là ví dụ về việc đặt tên relation cho một resource được export. Vị trí annotation và chữ ký method cần phù hợp với loại association hoặc query method trong repository thực tế.

## 9. HATEOAS: client nên điều hướng bằng liên kết

HATEOAS (Hypermedia as the Engine of Application State) coi các liên kết trong response là hướng dẫn cho trạng thái tiếp theo của client. Client không cần biết trước toàn bộ URL của mọi tài nguyên.

Một client theo HAL có thể làm việc theo trình tự:

1. Bắt đầu từ URI entry point mà ứng dụng công bố.
2. Đọc \`_links\` để tìm relation dẫn tới collection cần dùng.
3. Theo href của collection để tải danh sách.
4. Đọc \`_embedded\` để lấy các item hiện có.
5. Theo \`self\` của item để mở một entity cụ thể.
6. Theo link association để tải tài nguyên liên quan.
7. Theo \`next\` hoặc \`prev\` để chuyển trang.
8. Theo \`search\` để khám phá các query method mà repository công bố.

Cách làm này giúp client ít phụ thuộc vào cách server tổ chức URI. Nếu server thay đổi base path hoặc cách sinh link, client vẫn có thể hoạt động khi relation và entry point được giữ ổn định.

### Ví dụ điều hướng

Giả sử client nhận được:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/api/people"
    }
  }
}
~~~

Client đọc relation \`people\`, lấy href rồi gọi collection. Sau đó, nếu collection trả về link \`next\`, client theo chính href đó để tải trang tiếp theo.

Client không cần tự tạo \`/api/people?page=1\` nếu server đã đưa ra link \`next\`. Link do server trả về có thể mang theo sort, filter, page size hoặc các query parameter khác mà client cần giữ nguyên.

## 10. Dùng HAL trong HTTP client

Ví dụ dùng curl để lấy một item:

~~~bash
curl -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/42
~~~

Lấy collection có phân trang và sắp xếp:

~~~bash
curl -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=0&size=10&sort=lastName,asc"
~~~

Khi đọc response, client nên:

- Kiểm tra HTTP status trước khi parse body.
- Chọn parser hỗ trợ HAL hoặc đọc các trường HAL theo cấu trúc JSON.
- Xem \`_links\` như tập hợp các relation có thể điều hướng.
- Xem \`_embedded\` như nội dung resource được nhúng.
- Không giả định collection luôn có item.
- Không giả định mọi relation luôn xuất hiện.
- Không tự cố định page size hoặc tổng số trang trong logic điều hướng.
- Theo link server trả về khi chuyển trang hoặc mở association.

Nếu dùng Java và Spring HATEOAS để viết client hoặc custom controller, các abstraction như \`EntityModel\`, \`CollectionModel\` và \`PagedModel\` giúp biểu diễn entity, collection và page cùng các link. Spring Data REST tự tạo representation cho repository endpoint; ứng dụng không cần tự bọc response repository bằng các kiểu này chỉ để endpoint export mặc định hoạt động.

## 11. Projection và representation của item

Representation trả về có thể khác nhau tùy cấu hình projection. Projection cho phép định nghĩa một view gồm một tập thuộc tính hoặc association được chọn, phục vụ các trường hợp client không cần toàn bộ dữ liệu entity.

Khi dùng projection, client có thể nhận thêm hoặc thay đổi phần thuộc tính được hiển thị. Vì vậy:

- Không coi response JSON là bản sao nguyên vẹn của entity trong database.
- Dựa vào profile, link và hợp đồng API để hiểu representation.
- Kiểm tra projection đang được export và cách client yêu cầu projection.
- Không dùng projection như cơ chế authorization hoặc che giấu dữ liệu nhạy cảm thay cho security.

Projection ảnh hưởng nội dung representation; các khái niệm item, collection, link và pagination vẫn giữ vai trò riêng.

## 12. Những lỗi và nhầm lẫn thường gặp

1. **Tìm thuộc tính entity ở sai cấp JSON.** Với item resource, thuộc tính thường nằm ở cấp ngoài; với collection, item nằm trong \`_embedded\`.
2. **Coi \`_embedded.people\` là tên cố định.** Relation có thể được tùy chỉnh qua \`collectionResourceRel\`; hãy đọc đúng key mà server trả về.
3. **Coi \`page.number\` bắt đầu từ 1.** Mặc định Spring Data REST dùng chỉ số trang bắt đầu từ 0.
4. **Tự dựng URL trang kế tiếp.** Dùng relation \`next\` để giữ các query parameter và quy tắc URI mà server công bố.
5. **Giả định mọi response đều có \`next\` hoặc \`prev\`.** Link điều hướng phụ thuộc vị trí trang; trang đầu, trang cuối và collection một trang có tập link khác nhau.
6. **Giả định collection rỗng là lỗi.** Collection rỗng vẫn là response hợp lệ; client phải xử lý trường hợp không có item.
7. **Nhầm association link với object đã nhúng.** Link cho biết nơi truy cập association; client cần gọi href nếu muốn đọc resource đó.
8. **Dùng \`id\` để dựng URI thay vì theo self link.** Cấu trúc URI có thể thay đổi; link self là tham chiếu do server cung cấp.
9. **Gửi media type không phù hợp.** Kiểm tra header \`Accept\` và media type API hỗ trợ, thường là \`application/hal+json\` cho HAL.
10. **Cho rằng \`page.size\` luôn bằng giá trị client yêu cầu.** Server có thể áp dụng default hoặc maximum page size; đọc metadata của response.
11. **Cho rằng \`totalElements\` là tổng dữ liệu toàn hệ thống trong mọi trường hợp.** Đây là tổng theo truy vấn/điều kiện hiện tại của collection.
12. **Dùng tên relation như tên field Java.** Relation là hợp đồng hypermedia công bố ra API; nó có thể được tùy chỉnh độc lập với tên thuộc tính hoặc repository.

## 13. Checklist khi đọc hoặc debug response

Khi một client không hiển thị đúng dữ liệu từ Spring Data REST, hãy kiểm tra:

1. Request đang gọi item URI hay collection URI?
2. Header \`Accept\` có yêu cầu media type phù hợp, chẳng hạn \`application/hal+json\`, không?
3. Với item, các thuộc tính domain có nằm ở cấp ngoài và link cần thiết có trong \`_links\` không?
4. Với collection, relation thực tế trong \`_embedded\` tên gì?
5. Nếu collection có phân trang, \`page.number\`, \`page.size\`, \`page.totalElements\` và \`page.totalPages\` có giá trị gì?
6. Các relation \`first\`, \`prev\`, \`next\`, \`last\` nào đang được server trả về?
7. Client có theo href của link hay đang tự dựng URL?
8. Repository có cấu hình \`collectionResourceRel\`, \`path\`, projection hoặc association export làm thay đổi representation không?
9. Có query parameter sort/page/size nào bị thay đổi hoặc bị giới hạn bởi cấu hình server không?
10. Nếu link association không xuất hiện, association đó có được export và có bị ẩn bởi cấu hình không?

Khi debug, hãy lưu cả status code, response headers và body. Một body JSON hợp lệ có thể vẫn mang media type hoặc status khác với điều client mong đợi.

## 14. Nguyên tắc thiết kế client và API

- Dùng item resource để làm việc với một entity cụ thể.
- Dùng collection resource để khám phá và liệt kê các entity.
- Dùng page metadata và navigation links để xử lý tập dữ liệu lớn.
- Giữ relation name ổn định như một phần của hợp đồng API nếu có client phụ thuộc vào nó.
- Để client điều hướng qua href được server công bố.
- Xử lý trường hợp collection rỗng và link tùy chọn.
- Không nhúng quá nhiều association vào một response nếu client chỉ cần một phần dữ liệu.
- Chọn page size phù hợp với độ trễ mạng, kích thước response và chi phí truy vấn.
- Xem projection là cách chọn representation, không phải ranh giới bảo mật.

## Tóm tắt

Một item resource biểu diễn một entity với các thuộc tính domain và link của chính nó. Một collection resource biểu diễn nhiều item trong \`_embedded\`, đồng thời cung cấp link ở cấp collection. Khi collection được phân trang, Spring Data REST bổ sung object \`page\` và các relation điều hướng như \`first\`, \`prev\`, \`next\`, \`last\`.

HAL cung cấp cấu trúc JSON cho link và resource nhúng; HATEOAS định hướng client sử dụng các link đó để khám phá API. Client nên đọc relation, theo href, kiểm tra metadata phân trang và xử lý link tùy chọn thay vì phụ thuộc vào URL tự suy đoán.

## Tài liệu tham khảo

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL — Hypertext Application Language](https://stateless.group/hal_specification.html)
