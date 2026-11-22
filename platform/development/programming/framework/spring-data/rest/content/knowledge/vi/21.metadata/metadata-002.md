# ALPS mô tả thuộc tính và thao tác trên tài nguyên như thế nào

## Mục tiêu

ALPS (Application-Level Profile Semantics) là định dạng metadata mô tả ngữ nghĩa ở cấp ứng dụng của một tài nguyên và các thao tác có thể thực hiện trên tài nguyên đó. Spring Data REST tạo tài liệu ALPS cho mỗi repository được export. Nhờ đó, client có thể khám phá các thuộc tính, quan hệ và chuyển trạng thái REST mà API công bố, thay vì chỉ nhìn vào một JSON mẫu rồi tự suy đoán ý nghĩa.

ALPS bổ sung ngữ nghĩa cho hypermedia. Nó không thay thế dữ liệu HAL mà endpoint trả về, cũng không phải một schema xác thực dữ liệu đầy đủ. HAL mô tả representation và các liên kết trong phản hồi; ALPS giải thích ý nghĩa của những phần tử và thao tác được công bố.

## 1. Tìm tài liệu ALPS trong Spring Data REST

Spring Data REST công bố metadata qua liên kết quan hệ `profile`.

Giả sử ứng dụng có hai repository được export là `persons` và `addresses`. Tài liệu gốc của API có thể chứa:

~~~json
{
  "_links": {
    "persons": {
      "href": "http://localhost:8080/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/addresses"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Luồng khám phá metadata:

1. Gọi `GET /` để lấy tài liệu gốc và tìm liên kết `profile`.
2. Gọi `GET /profile` để xem danh sách profile của từng repository.
3. Theo liên kết `/profile/persons` để lấy ALPS profile mô tả tài nguyên Person.
4. Theo liên kết profile của repository liên quan, chẳng hạn `/profile/addresses`, khi cần hiểu một quan hệ.

Ví dụ, `GET /profile` trả về chỉ mục các profile:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "persons": {
      "href": "http://localhost:8080/profile/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/profile/addresses"
    }
  }
}
~~~

Ở cấp gốc chỉ có một liên kết `profile`; phải đi tiếp tới `/profile` để tìm metadata của từng tài nguyên. Collection resource cũng có liên kết `profile` trỏ trực tiếp tới profile tương ứng, ví dụ `/profile/persons`.

Có thể yêu cầu ALPS bằng HTTP:

~~~bash
curl -H "Accept: application/alps+json" \
  http://localhost:8080/profile/persons
~~~

Profile thường được Spring Data REST phục vụ tại đường dẫn trên. Media type của tài liệu là `application/alps+json`, khác với `application/hal+json` của representation HAL.

## 2. Cấu trúc cơ bản của ALPS profile

Một ALPS document thường có phiên bản và danh sách descriptor:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "lastName",
          "type": "SEMANTIC"
        }
      ]
    }
  ]
}
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| `version` | Phiên bản định dạng ALPS được dùng trong tài liệu. |
| `descriptors` | Danh sách descriptor ở cấp hiện tại; có thể lồng descriptor con. |
| `id` | Định danh descriptor, thường được dùng làm fragment trong `rt`. |
| `name` | Tên thuộc tính hoặc tên hypermedia control mà descriptor mô tả. |
| `type` | Phân loại descriptor theo ngữ nghĩa dữ liệu hoặc loại chuyển trạng thái. |
| `rt` | Resource type mà descriptor trả về hoặc liên kết tới; thường tham chiếu một descriptor bằng fragment. |
| `doc` | Mô tả bằng ngôn ngữ tự nhiên cho descriptor hoặc representation. |

Trong ví dụ, `person-representation` gom các thuộc tính của một tài nguyên Person. Các descriptor con mô tả từng phần tử như `firstName` và `lastName`.

## 3. ALPS mô tả thuộc tính và quan hệ như thế nào?

### Thuộc tính dữ liệu

Thuộc tính mang dữ liệu của representation thường được đánh dấu `SEMANTIC`:

~~~json
{
  "name": "firstName",
  "type": "SEMANTIC"
}
~~~

Descriptor này cho biết representation có phần tử mang tên `firstName`. ALPS đang mô tả ý nghĩa và tên của phần tử; chỉ nhìn descriptor này không thể suy ra đầy đủ kiểu dữ liệu, độ dài tối đa, quy tắc bắt buộc hay toàn bộ ràng buộc validation của trường.

Một số thuộc tính kỹ thuật như `id` cũng có thể xuất hiện trong profile. Vì vậy, hãy xem ALPS là metadata về ngữ nghĩa của mô hình và API, không giả định mọi descriptor đều tương ứng với một trường mà client luôn nhìn thấy trong mọi response.

### Quan hệ tới tài nguyên khác

Một thuộc tính quan hệ có thể được biểu diễn như một hypermedia control. Ví dụ Person có quan hệ `address` tới tài nguyên Address:

~~~json
{
  "name": "address",
  "type": "SAFE",
  "rt": "http://localhost:8080/profile/addresses#address"
}
~~~

Ở đây:

- `name: address` xác định quan hệ được công bố.
- `type: SAFE` cho biết client có thể theo liên kết để thực hiện một chuyển trạng thái an toàn, thường là GET.
- `rt` tham chiếu tới descriptor `address` trong profile của tài nguyên Address, giúp client biết kiểu tài nguyên đích.

Sự khác biệt này rất hữu ích: một trường đơn giản như `firstName` mô tả dữ liệu, còn `address` có thể là liên kết điều hướng tới tài nguyên khác. Client có thể theo liên kết và tiếp tục khám phá profile của tài nguyên đích.

## 4. ALPS mô tả thao tác REST như thế nào?

Ngoài representation, ALPS liệt kê các thao tác mà repository resource hỗ trợ. Mỗi thao tác là một descriptor có định danh, tên control, loại chuyển trạng thái và kiểu tài nguyên liên quan.

Bốn giá trị `type` quan trọng:

| Type | Ý nghĩa | Ví dụ HTTP |
|---|---|---|
| `SEMANTIC` | Phần tử dữ liệu hoặc trạng thái trong representation. | Thuộc tính `firstName`. |
| `SAFE` | Chuyển trạng thái an toàn, không làm thay đổi trạng thái server. | `GET`, `HEAD`. |
| `IDEMPOTENT` | Chuyển trạng thái có thay đổi server nhưng lặp lại cùng yêu cầu có cùng hiệu ứng cuối. | `PUT`, `DELETE`. |
| `UNSAFE` | Chuyển trạng thái không an toàn và không idempotent. | `POST`. |

Ví dụ, các thao tác thường xuất hiện trong profile của Person:

~~~json
[
  {
    "id": "create-persons",
    "name": "persons",
    "type": "UNSAFE",
    "rt": "#person-representation"
  },
  {
    "id": "get-persons",
    "name": "persons",
    "type": "SAFE",
    "rt": "#person-representation"
  },
  {
    "id": "delete-person",
    "name": "person",
    "type": "IDEMPOTENT",
    "rt": "#person-representation"
  },
  {
    "id": "patch-person",
    "name": "person",
    "type": "UNSAFE",
    "rt": "#person-representation"
  },
  {
    "id": "update-person",
    "name": "person",
    "type": "IDEMPOTENT",
    "rt": "#person-representation"
  },
  {
    "id": "get-person",
    "name": "person",
    "type": "SAFE",
    "rt": "#person-representation"
  }
]
~~~

Cách đọc:

- `create-persons` là thao tác tạo Person trên collection `persons`. Tên số nhiều cho biết thao tác áp dụng lên collection; POST có thể tạo một phần tử mới.
- `get-persons` đọc collection, còn `get-person` đọc một phần tử.
- `update-person` biểu diễn cập nhật theo cách idempotent, thường tương ứng PUT.
- `patch-person` biểu diễn cập nhật một phần representation theo cách không được xem là idempotent.
- `delete-person` biểu diễn xóa một tài nguyên; lặp lại cùng thao tác không làm thay đổi thêm trạng thái cuối.

Trường `rt` trong các descriptor thao tác trỏ tới `#person-representation`, nghĩa là kết quả hoặc kiểu tài nguyên liên quan là representation Person. `id` phân biệt từng thao tác; `name` cho biết control gắn với collection hay item.

Các descriptor này mô tả những chuyển trạng thái Spring Data REST công bố cho repository. Chúng không phải danh sách tất cả method Java trong repository và cũng không thay thế việc kiểm tra quyền truy cập, validation hay điều kiện nghiệp vụ ở server.

## 5. Projection xuất hiện trong ALPS như thế nào?

Nếu repository khai báo projection, Spring Data REST đưa chúng vào metadata của những thao tác GET liên quan. Một descriptor `projection` được lồng bên trong descriptor thao tác, rồi liệt kê các projection có thể chọn và các thuộc tính mà từng projection cung cấp.

Ví dụ rút gọn:

~~~json
{
  "id": "get-persons",
  "name": "persons",
  "type": "SAFE",
  "rt": "#person-representation",
  "descriptors": [
    {
      "name": "projection",
      "type": "SEMANTIC",
      "descriptors": [
        {
          "name": "inlineAddress",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "address",
              "type": "SEMANTIC"
            },
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        },
        {
          "name": "noAddresses",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        }
      ]
    }
  ]
}
~~~

Trong ví dụ:

- `projection` là tham số lựa chọn cách render representation.
- `inlineAddress` cung cấp `address`, `firstName` và `lastName`.
- `noAddresses` chỉ cung cấp `firstName` và `lastName`.

Client có thể đọc metadata để biết projection nào được hỗ trợ và các trường nào có trong từng projection, sau đó lựa chọn projection phù hợp theo cơ chế của API.

## 6. Bổ sung mô tả dễ hiểu bằng rest-messages.properties

Tên thuộc tính như `firstName` hoặc `address` chưa giải thích đầy đủ ý nghĩa nghiệp vụ. Spring Data REST cho phép bổ sung nội dung mô tả vào ALPS bằng file `rest-messages.properties`.

Ví dụ đặt trong classpath resources:

~~~properties
rest.description.person=A collection of people
rest.description.person.id=Primary key used internally to store a person
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
rest.description.person.address=Person's address
~~~

Các key có ý nghĩa:

- `rest.description.person` mô tả toàn bộ representation Person.
- `rest.description.person.firstName` mô tả thuộc tính `firstName`.
- `rest.description.person.address` mô tả quan hệ `address`.
- `rest.description.person.id` bổ sung mô tả cho thuộc tính định danh.

Sau khi cấu hình, descriptor tương ứng có thêm phần `doc`:

~~~json
{
  "name": "firstName",
  "doc": {
    "value": "Person's first name",
    "format": "TEXT"
  },
  "type": "SEMANTIC"
}
~~~

Phần `doc` là lời giải thích cho con người và client; nó không tự đổi tên thuộc tính, thay đổi endpoint hoặc áp dụng validation. Spring MVC hỗ trợ locale, do đó có thể cung cấp các file message theo ngôn ngữ để mô tả metadata phù hợp với client.

## 7. ALPS giúp client làm gì?

Một client có thể dùng ALPS để:

1. **Khám phá cấu trúc:** biết representation có những thuộc tính và quan hệ nào.
2. **Hiểu liên kết:** phân biệt dữ liệu thông thường với liên kết an toàn dẫn tới tài nguyên khác.
3. **Khám phá thao tác:** nhận biết API có thao tác đọc, tạo, cập nhật hoặc xóa ở collection và item.
4. **Xây dựng giao diện tổng quát:** dựa vào descriptor để hiển thị trường, lựa chọn liên kết và lựa chọn thao tác phù hợp.
5. **Khám phá projection:** biết các cách biểu diễn thay thế mà server công bố.
6. **Hiển thị hướng dẫn:** sử dụng phần `doc` để giải thích thuộc tính và thao tác cho người dùng.

ALPS giúp client giảm phụ thuộc vào tên endpoint được hard-code. Tuy nhiên, metadata không bảo đảm thao tác sẽ thành công: server vẫn có thể từ chối do xác thực, phân quyền, validation, trạng thái tài nguyên hoặc quy tắc nghiệp vụ.

## 8. Phân biệt ALPS, HAL và JSON Schema

| Cơ chế | Câu hỏi mà nó trả lời | Vai trò |
|---|---|---|
| HAL (`application/hal+json`) | Tài nguyên hiện tại có dữ liệu và liên kết nào? | Representation hypermedia trong response. |
| ALPS (`application/alps+json`) | Các thuộc tính và chuyển trạng thái được công bố mang ý nghĩa gì? | Profile ngữ nghĩa của API. |
| JSON Schema (`application/schema+json`) | Cấu trúc dữ liệu có kiểu và ràng buộc hình dạng ra sao? | Mô tả cấu trúc, hữu ích cho kiểm tra dữ liệu. |

Spring Data REST dùng cùng profile URI để cung cấp các dạng metadata khác nhau theo media type. Ví dụ:

~~~bash
# ALPS metadata
curl -H "Accept: application/alps+json" \
  http://localhost:8080/profile/persons

# JSON Schema metadata
curl -H "Accept: application/schema+json" \
  http://localhost:8080/profile/persons
~~~

Không nên dùng ALPS thay cho JSON Schema khi cần biết kiểu dữ liệu, định dạng hoặc ràng buộc cấu trúc. Ngược lại, JSON Schema không thể hiện đầy đủ ngữ nghĩa của các chuyển trạng thái hypermedia như ALPS.

## 9. Cách kiểm tra khi ALPS thiếu hoặc không đúng

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Không tìm thấy liên kết `profile` ở tài liệu gốc | Repository có được Spring Data REST phát hiện và export không; kiểm tra cấu hình base path và tài liệu gốc. |
| `/profile` không có repository mong đợi | Repository có bị tắt export bằng `exported = false` hoặc cấu hình tương đương không. |
| `/profile/{rel}` không trả về profile mong muốn | Kiểm tra relation/path thực tế mà repository công bố và theo đúng liên kết từ `/profile`. |
| Thiếu thuộc tính trong representation descriptor | Kiểm tra domain type, thuộc tính được export và cấu hình serialization/projection liên quan. |
| Thiếu thao tác create/update/delete | Kiểm tra method được export, cấu hình repository và các phương thức bị ẩn bằng `@RestResource(exported = false)`. |
| Quan hệ không trỏ tới profile đích | Kiểm tra repository của tài nguyên liên quan đã được export và `rt` có tham chiếu đúng profile/descriptor hay chưa. |
| Thiếu lời giải thích trong `doc` | Kiểm tra tên key trong `rest-messages.properties`, vị trí file resources và locale đang được sử dụng. |
| Client hiểu sai kiểu descriptor | Đối chiếu `type`: `SEMANTIC`, `SAFE`, `IDEMPOTENT`, `UNSAFE`; không coi chúng là kiểu dữ liệu Java. |

Khi kiểm tra, hãy bắt đầu từ liên kết `profile` mà server trả về, theo liên kết tới profile repository, rồi đối chiếu descriptor cụ thể. Cách này tránh phụ thuộc vào đường dẫn suy đoán hoặc tài liệu cũ.

## Ghi nhớ

ALPS mô tả tài nguyên theo hai lớp chính. Lớp representation dùng descriptor, thường có `type: SEMANTIC`, để nêu các thuộc tính; quan hệ tới tài nguyên khác có thể là hypermedia control kiểu `SAFE` và trỏ tới profile đích bằng `rt`. Lớp thao tác dùng các descriptor như `get-persons`, `create-persons`, `update-person` và `delete-person`, phân loại bằng `SAFE`, `UNSAFE` hoặc `IDEMPOTENT`. Spring Data REST công bố tài liệu này qua `/profile` và `/profile/{rel}`; projection và mô tả tùy chỉnh cũng có thể được phản ánh trong metadata.

## Tài liệu tham khảo

- [Spring Data REST Reference — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Application-Level Profile Semantics (ALPS) Specification](https://alps.io/spec/drafts/draft-00.html)
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
