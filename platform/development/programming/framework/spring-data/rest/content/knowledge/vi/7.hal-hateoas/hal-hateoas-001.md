# Cấu trúc biểu diễn HAL với _links, _embedded và dữ liệu nghiệp vụ

## Mục tiêu

Spring Data REST thường trả về resource dưới dạng HAL JSON. Khi đọc một response, cần nhận ra ba nhóm thành phần:

- `_links` mô tả các URI mà client có thể đi tới, cùng quan hệ của từng link.
- `_embedded` chứa representation của resource khác được nhúng trong response hiện tại.
- Các thuộc tính còn lại biểu diễn dữ liệu nghiệp vụ của domain object, chẳng hạn `id`, `name`, `status` hoặc `createdAt`.

Ba nhóm này kết hợp để tạo một representation có cả dữ liệu và khả năng điều hướng. Client có thể hiển thị dữ liệu ngay, đồng thời dùng các link để khám phá thao tác hoặc resource tiếp theo.

## 1. HATEOAS và HAL là hai khái niệm liên quan nhưng khác nhau

**HATEOAS** (Hypertext As The Engine Of Application State) là một ràng buộc kiến trúc REST: response cung cấp hypermedia controls để client biết có thể tiếp tục đi đâu và thực hiện bước nào. Client bắt đầu từ một entry point đã biết, đọc các link và theo link phù hợp với mục tiêu; client không cần tự ghép mọi URL theo quy ước nội bộ của server.

**HAL** (Hypertext Application Language) là một định dạng biểu diễn hypermedia dành cho JSON. HAL quy ước hai thuộc tính đặc biệt:

- `_links`: tập hợp các link được nhóm theo link relation.
- `_embedded`: các resource được nhúng trong representation hiện tại, cũng được nhóm theo relation.

Có thể hiểu:

- HATEOAS trả lời câu hỏi **API nên cung cấp khả năng điều hướng như thế nào**.
- HAL trả lời câu hỏi **các link và resource nhúng được biểu diễn trong JSON theo cấu trúc nào**.

HAL là một cách triển khai hypermedia, không phải toàn bộ HATEOAS. Một API có thể dùng định dạng hypermedia khác; ngược lại, một JSON có trường `_links` nhưng client vẫn bỏ qua các link và hard-code URL thì chưa tận dụng đầy đủ ý tưởng HATEOAS.

## 2. Khung tổng quát của một HAL representation

Một representation HAL có thể chứa link, resource nhúng và dữ liệu riêng của resource:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "orders": {
      "href": "https://api.example.com/people/42/orders"
    }
  },
  "id": 42,
  "name": "Nguyen An",
  "status": "ACTIVE",
  "_embedded": {
    "department": {
      "id": 7,
      "name": "Engineering",
      "_links": {
        "self": {
          "href": "https://api.example.com/departments/7"
        }
      }
    }
  }
}
~~~

Đọc response trên theo từng phần:

1. `_links.self.href` xác định URI của chính resource Person.
2. `_links.orders.href` chỉ tới resource đơn hàng liên quan. Đây là link điều hướng; client có thể gọi URI đó khi cần.
3. `id`, `name`, `status` là dữ liệu nghiệp vụ của Person.
4. `_embedded.department` là representation của Department được nhúng ngay trong response. Nó có dữ liệu riêng và có thể có `_links` riêng.

Tên `_links` và `_embedded` là các thuộc tính dành riêng của HAL. Các thuộc tính nghiệp vụ thường nằm cùng cấp với chúng, không cần bọc thêm trong một object `data` do HAL quy định. HAL không bắt buộc mọi API phải có một schema nghiệp vụ giống nhau; schema của các field như `name`, `status` vẫn do ứng dụng định nghĩa.

## 3. Cấu trúc của _links

`_links` là một JSON object. Mỗi key là một **link relation** (tên quan hệ); value mô tả một link hoặc nhiều link cùng relation.

### 3.1. Một link object

Một link object cần có `href`. Các thuộc tính khác có thể xuất hiện tùy trường hợp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `href` | URI hoặc URI reference mà client có thể truy cập |
| `templated` | `true` khi href là URI template có biến cần thay thế; mặc định có thể hiểu là false nếu không khai báo |
| `type` | Media type dự kiến của representation tại link đích |
| `deprecation` | URI cung cấp thông tin về việc link relation bị deprecated |
| `name` | Tên phân biệt một link khi có nhiều link cùng relation |
| `profile` | URI mô tả profile của resource hoặc link |
| `title` | Nhãn thân thiện để trình bày cho người dùng |
| `hreflang` | Ngôn ngữ của resource đích |

Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42",
      "type": "application/hal+json",
      "title": "Person 42"
    }
  }
}
~~~

Client nên coi `href` là URI do server công bố. Không nên tự thay segment, đoán ID hoặc ghép URL từ tên relation. URI có thể thay đổi khi server đổi cấu hình; relation mới là nhãn ngữ nghĩa cho biết link dùng để làm gì.

### 3.2. Link relation

Relation cho biết ý nghĩa của link. Một số relation thường gặp:

| Relation | Ý nghĩa thường gặp |
|---|---|
| `self` | Resource hiện tại |
| `next` | Trang tiếp theo của collection |
| `prev` | Trang trước |
| `first` | Trang đầu |
| `last` | Trang cuối |
| `profile` | Thông tin mô tả profile/schema liên quan |
| `search` | Điểm khám phá các truy vấn tìm kiếm |
| `collection` | Collection chứa resource, nếu API công bố relation này |

Tên relation là phần quan trọng của hypermedia contract. Ví dụ, client có thể tìm relation `next` để đi tiếp mà không cần tự tính URL trang sau. Một API có thể dùng relation chuẩn hoặc relation mở rộng theo miền nghiệp vụ.

### 3.3. Nhiều link cùng relation

Khi một relation có nhiều link, value của relation có thể là một mảng:

~~~json
{
  "_links": {
    "alternate": [
      {
        "href": "https://api.example.com/people/42",
        "type": "application/hal+json"
      },
      {
        "href": "https://api.example.com/people/42.csv",
        "type": "text/csv"
      }
    ]
  }
}
~~~

Vì vậy, client không nên giả định mọi value trong `_links` luôn là một object duy nhất. Nếu API trả mảng, client cần duyệt các link và có thể dùng `type` hoặc `name` để chọn representation phù hợp.

### 3.4. URI template và thuộc tính templated

Collection endpoint thường hỗ trợ query parameter cho phân trang hoặc sắp xếp. Server có thể công bố URI template:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people{?page,size,sort}",
      "templated": true
    }
  }
}
~~~

`templated: true` báo cho client biết href chứa biến template. Client cần mở rộng template theo quy tắc URI Template trước khi gửi request, ví dụ điền `page=0` và `size=20`. Nếu `templated` không phải true, hãy dùng href như một URI hoàn chỉnh.

### 3.5. CURIE cho relation mở rộng

HAL hỗ trợ CURIE (Compact URI) để rút gọn tên relation mở rộng. Ví dụ:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:manager": {
      "href": "https://api.example.com/people/42/manager"
    }
  }
}
~~~

Relation `ex:manager` được giải thích thông qua CURIE có tên `ex`. Client có thể dùng tên relation này như một định danh ngữ nghĩa; không nên tự coi nó là đường dẫn URL.

## 4. Cấu trúc của _embedded

`_embedded` chứa representation của resource khác được đưa vào response hiện tại. Mỗi key trong `_embedded` là relation của resource được nhúng.

Giá trị có thể là một resource object:

~~~json
{
  "_embedded": {
    "department": {
      "id": 7,
      "name": "Engineering",
      "_links": {
        "self": {
          "href": "https://api.example.com/departments/7"
        }
      }
    }
  }
}
~~~

Hoặc là một mảng resource, thường gặp khi nhúng collection:

~~~json
{
  "_embedded": {
    "people": [
      {
        "id": 42,
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/42"
          }
        }
      },
      {
        "id": 43,
        "name": "Tran Binh",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/43"
          }
        }
      }
    ]
  }
}
~~~

Mỗi embedded resource có thể chứa dữ liệu nghiệp vụ, `_links` của riêng nó và thậm chí `_embedded` lồng nhau. Điều đó cho phép client hiển thị một phần quan hệ ngay trong response mà không phải gửi thêm request cho từng item.

### 4.1. Link và embedded khác nhau thế nào?

| Tiêu chí | `_links` | `_embedded` |
|---|---|---|
| Mục đích | Công bố URI để điều hướng | Đưa representation của resource liên quan vào response |
| Nội dung | Link object chứa href và metadata | Resource object hoặc mảng resource |
| Dữ liệu nghiệp vụ | Thường không chứa dữ liệu của resource đích | Có thể chứa các field nghiệp vụ của resource được nhúng |
| Chi phí request | Client gửi request riêng khi cần theo link | Dữ liệu đã có trong response hiện tại |
| Mức độ hiện diện | Chỉ có các relation mà server công bố | Chỉ có các resource server chọn nhúng |

Một association link không có nghĩa resource đích đã được nhúng. Ví dụ, Person có link `department` trỏ đến Department nhưng response không có `_embedded.department`. Khi đó client phải theo link nếu cần dữ liệu Department.

Ngược lại, một resource có thể xuất hiện trong `_embedded` để client hiển thị nhanh, đồng thời vẫn có link `self` để truy cập trực tiếp sau này. Embedded data là representation tại thời điểm response được tạo; client không nên xem nó như một bản sao luôn đồng bộ.

### 4.2. _embedded là tùy chọn

Không phải response HAL nào cũng có `_embedded`. Nếu server chỉ trả link, client vẫn có thể điều hướng theo các link đó. Client cũng không nên giả định mọi association đều được nhúng, hoặc mọi collection luôn trả cùng một cấu trúc embedded khi projection, cấu hình hoặc loại resource thay đổi.

## 5. Dữ liệu nghiệp vụ nằm ở đâu?

Các field nghiệp vụ mô tả resource hiện tại thường nằm ở cấp cao nhất của representation, cùng cấp với `_links` và `_embedded`.

Ví dụ một Person resource:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "active": true,
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "department": {
      "href": "https://api.example.com/people/42/department"
    }
  }
}
~~~

Trong ví dụ này:

- `id`, `firstName`, `lastName`, `email`, `active` là dữ liệu nghiệp vụ.
- `_links.self` trỏ tới Person hiện tại.
- `_links.department` chỉ tới association Department.

HAL không định nghĩa ý nghĩa hoặc kiểu dữ liệu của `firstName`, `email` hay `active`; điều đó thuộc API/domain model. HAL chỉ dành ra các tên đặc biệt như `_links` và `_embedded` để biểu diễn hypermedia.

Tránh dùng tên field nghiệp vụ trùng với các thuộc tính dành riêng của HAL. Nếu cần một object nghiệp vụ lồng nhau, hãy thiết kế nó theo schema domain của ứng dụng, không nhầm object đó với embedded resource có relation trong `_embedded`.

## 6. Spring Data REST thường biểu diễn resource như thế nào?

Spring Data REST dùng Spring HATEOAS để tạo representation có link. Khi làm việc với API Spring Data REST, có thể bắt đầu từ root resource, sau đó theo link collection, item, search hoặc association.

Ví dụ các response dưới đây mang tính minh họa; tên relation, base path, metadata phân trang và nội dung nhúng phụ thuộc cấu hình ứng dụng.

### 6.1. Root resource

Request:

~~~http
GET /api
Accept: application/hal+json
~~~

Response có thể công bố các collection:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/api/people"
    },
    "departments": {
      "href": "https://api.example.com/api/departments"
    },
    "profile": {
      "href": "https://api.example.com/api/profile"
    }
  }
}
~~~

Client đọc relation `people` để biết collection Person nằm ở đâu. Nếu server đổi base path hoặc collection path, client vẫn có thể bắt đầu từ root và sử dụng link mới.

### 6.2. Collection resource

Request:

~~~http
GET /api/people?page=0&size=20
Accept: application/hal+json
~~~

Một response collection điển hình:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/people/42"
          }
        }
      },
      {
        "firstName": "Binh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/people/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people{?page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "https://api.example.com/api/profile/people"
    },
    "search": {
      "href": "https://api.example.com/api/people/search"
    },
    "next": {
      "href": "https://api.example.com/api/people?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 37,
    "totalPages": 2,
    "number": 0
  }
}
~~~

Trong response này:

- `_embedded.people` chứa các Person resource của trang hiện tại.
- Mỗi Person có link `self` riêng để mở item.
- `_links.self` trỏ tới collection và thể hiện các tham số truy vấn có thể thay đổi.
- `_links.search` giúp client khám phá query resource.
- `_links.next` cho biết trang tiếp theo.
- `page` là metadata phân trang do Spring Data REST thường cung cấp cho collection có paging.

Client không nên tự tính đường dẫn trang kế tiếp nếu response đã cung cấp relation `next`. Khi không có `next`, client hiểu rằng server không công bố trang tiếp theo trong trạng thái hiện tại.

### 6.3. Item resource

Request:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Response minh họa:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    },
    "department": {
      "href": "https://api.example.com/api/people/42/department"
    }
  }
}
~~~

Các field Person nằm ở root; link association Department được công bố trong `_links`. Nếu server không nhúng Department, client gọi link `department` khi cần thông tin liên quan. Nếu projection hoặc cấu hình cho phép nhúng, representation có thể có thêm `_embedded.department`.

### 6.4. Media type

HAL JSON thường được trao đổi với media type:

~~~http
Accept: application/hal+json
~~~

Response HAL tương ứng thường có:

~~~http
Content-Type: application/hal+json
~~~

Media type giúp client và server thống nhất định dạng representation. Khi debug, hãy kiểm tra cả body JSON và header Content-Type; một JSON thông thường không nhất thiết tuân theo cấu trúc HAL.

## 7. Tùy chỉnh relation trong Spring Data REST

Tên relation mà client nhìn thấy có thể được điều khiển bằng annotation. Ví dụ:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Ở đây:

- `path = "people"` xác định collection path.
- `collectionResourceRel = "people"` đặt relation của collection được công bố trong hypermedia.

Với query method, `@RestResource` có thể đặt path và relation:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
Page<Person> findByLastName(
        @Param("lastName") String lastName,
        Pageable pageable);
~~~

Client sẽ khám phá query qua search resource và theo relation/path mà server công bố. Khi thay đổi relation, hãy xem đó là thay đổi hypermedia contract mà client sử dụng; cập nhật client theo relation mới hoặc giữ tương thích nếu có yêu cầu versioning.

Projection và excerpt cũng có thể làm thay đổi các field được serialize hoặc cách association được trình bày. Vì vậy, đừng suy ra rằng mọi entity đều luôn có cùng danh sách business fields hoặc cùng cấu trúc `_embedded`.

## 8. Cách client nên đọc và điều hướng HAL

Một client HATEOAS nên thực hiện quy trình sau:

1. Gọi entry point đã biết, ví dụ `/api`.
2. Đọc `_links` và tìm relation tương ứng với mục tiêu, chẳng hạn `people`.
3. Gửi request tới `href` của relation đó.
4. Đọc các business fields để hiển thị dữ liệu.
5. Nếu cần resource liên quan, kiểm tra `_embedded` trước; nếu chưa có dữ liệu, tìm relation tương ứng trong `_links` và theo href.
6. Với collection, theo `next`, `prev`, `first` hoặc `last` nếu được cung cấp.
7. Với query resource, theo link `search` và các link truy vấn do server công bố.

Ví dụ logic điều hướng:

~~~text
GET /api
   |
   +-- _links.people.href
             |
             v
       GET collection
             |
             +-- _embedded.people -> hiển thị danh sách
             |
             +-- _links.next -> trang tiếp theo
             |
             +-- _links.search -> khám phá truy vấn
~~~

Client nên dựa vào relation và href được trả về, không dựa vào quy tắc ghép URL như `/people/{id}/department`. Điều này giúp server có thể đổi đường dẫn mà không buộc client phải biết cấu trúc route nội bộ.

Khi đọc link template, client phải kiểm tra `templated`. Khi một relation trả về mảng, client phải xử lý nhiều link. Khi `_embedded` vắng mặt, client vẫn có thể dùng link để lấy resource.

## 9. Lỗi thường gặp khi đọc HAL

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Coi `_links` là dữ liệu nghiệp vụ | Đây là metadata điều hướng; business fields nằm ở các thuộc tính resource |
| Coi `href` là tên route cố định | Hãy dùng URI server công bố, không tự ghép path |
| Giả định mọi relation có một link object | Một relation có thể chứa mảng nhiều link |
| Giả định mọi resource liên quan đều có trong `_embedded` | Embedded là tùy chọn; resource có thể chỉ được công bố bằng link |
| Coi `_embedded` là bản sao đồng bộ của database | Đây là representation được nhúng tại thời điểm response |
| Bỏ qua `templated` | URI template cần được mở rộng trước khi gọi |
| Coi HAL là schema nghiệp vụ | HAL quy định cấu trúc hypermedia; domain fields do ứng dụng quyết định |
| Hard-code URL và bỏ qua relation | Client sẽ dễ hỏng khi server thay đổi path hoặc base path |

## 10. Checklist debug response

Khi một client không đọc được response Spring Data REST như mong đợi, kiểm tra:

1. Request có dùng Accept phù hợp, ví dụ `application/hal+json`, không?
2. Response Content-Type có phải HAL JSON không?
3. Body có `_links` không? Relation cần tìm được đặt tên gì?
4. Value của relation là object hay array?
5. Link có `templated: true` không? Nếu có, client đã mở rộng URI template chưa?
6. Resource liên quan nằm trong `_embedded` hay chỉ có link trong `_links`?
7. Relation collection có khớp `collectionResourceRel` được cấu hình không?
8. Projection/excerpt có làm thay đổi field hoặc embedded association không?
9. Client có đang hard-code URL thay vì theo href từ response không?

Một cách kiểm tra nhanh là gửi request với header:

~~~bash
curl -H "Accept: application/hal+json" https://api.example.com/api/people
~~~

Sau đó kiểm tra đồng thời các business fields, `_links`, `_embedded`, media type và metadata phân trang.

## 11. Ghi nhớ

- **HATEOAS** là nguyên tắc điều hướng ứng dụng qua hypermedia controls.
- **HAL** là định dạng JSON chuẩn hóa cách biểu diễn link và resource nhúng.
- **`_links`** cho biết có thể đi đâu và relation của link đó.
- **`_embedded`** chứa representation của resource liên quan được nhúng.
- **Business fields** mô tả resource hiện tại và do domain/API quyết định.
- Client nên bắt đầu từ entry point, đọc relation, theo href và xử lý URI template; không nên phụ thuộc vào URL tự ghép.

## Tài liệu tham khảo

- [HAL — Hypertext Application Language](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal)
- [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)

