# GET quan hệ đơn và quan hệ tập hợp trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết link của một quan hệ trong representation của entity.
- Gọi GET endpoint để lấy một đối tượng liên kết đơn.
- Gọi GET endpoint để lấy danh sách đối tượng liên kết.
- Đọc cấu trúc HAL JSON và xử lý các trường hợp endpoint không được export.

## 1. Association resource trong Spring Data REST

Spring Data REST tự động tạo REST endpoint từ các repository được export. Khi một entity có thuộc tính tham chiếu đến entity khác, Spring Data REST có thể công bố association resource để client truy cập quan hệ đó.

Ví dụ mô hình đơn hàng:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

Một đơn hàng có một khách hàng và có nhiều dòng hàng. Repository có thể được export như sau:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}

@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

@RepositoryRestResource(path = "order-lines")
public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {
}
~~~

Với cấu hình mặc định và các association được export, client có thể truy cập:

- Resource của một đơn hàng: **GET /orders/42**
- Association đơn customer: **GET /orders/42/customer**
- Association tập hợp lines: **GET /orders/42/lines**

Các đường dẫn trên minh họa theo tên repository và thuộc tính trong ví dụ. Đường dẫn thực tế phụ thuộc cấu hình export và các annotation tùy chỉnh.

## 2. Tìm association link từ item resource

Không nên tự ghép URL khi server đã cung cấp link. Trước tiên, gọi item resource:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

Representation HAL có thể chứa các link tương tự:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "purchaseOrder": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    },
    "lines": {
      "href": "http://localhost:8080/orders/42/lines"
    }
  }
}
~~~

Trong đó:

- **self** trỏ đến chính item resource.
- **customer** trỏ đến association đơn.
- **lines** trỏ đến association tập hợp.

Tên relation trong **_links** được tạo từ metadata của Spring Data REST. Hãy dùng đúng **href** server trả về; không giả định tên relation luôn giống tên Java class hoặc luôn dùng một đường dẫn cố định.

## 3. GET một quan hệ đơn

Với thuộc tính có cardinality đơn như **@ManyToOne** hoặc **@OneToOne**, association endpoint trỏ đến một đối tượng liên quan.

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

Ví dụ response:

~~~json
{
  "id": 7,
  "name": "Nguyen An",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/7"
    },
    "customer": {
      "href": "http://localhost:8080/customers/7"
    }
  }
}
~~~

Client nhận representation của khách hàng được liên kết với đơn hàng 42. Link **self** của response thường trỏ đến item resource của khách hàng; vì vậy có thể tiếp tục điều hướng đến resource đó hoặc theo các link khác mà server công bố.

Cần phân biệt hai URL:

- **GET /customers/7**: truy cập khách hàng theo định danh của khách hàng.
- **GET /orders/42/customer**: truy cập khách hàng thông qua quan hệ customer của đơn hàng 42.

Hai URL có thể dẫn đến cùng một đối tượng, nhưng URL association thể hiện cách client đi từ resource cha đến resource liên quan.

## 4. GET một quan hệ tập hợp

Với thuộc tính có cardinality nhiều như **@OneToMany** hoặc **@ManyToMany**, association endpoint trả về collection resource.

~~~http
GET /orders/42/lines
Accept: application/hal+json
~~~

Ví dụ response HAL:

~~~json
{
  "_embedded": {
    "orderLines": [
      {
        "id": 100,
        "productName": "Keyboard",
        "quantity": 1,
        "_links": {
          "self": {
            "href": "http://localhost:8080/order-lines/100"
          }
        }
      },
      {
        "id": 101,
        "productName": "Mouse",
        "quantity": 2,
        "_links": {
          "self": {
            "href": "http://localhost:8080/order-lines/101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42/lines"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 2,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Các phần cần đọc:

- **_embedded** chứa các item của collection. Tên key bên trong thường là relation của repository được export.
- Mỗi item có thể có **_links.self** để client truy cập trực tiếp item resource.
- **page** xuất hiện khi representation có thông tin phân trang; các giá trị cho biết kích thước trang, tổng số phần tử, tổng số trang và chỉ số trang hiện tại.
- **_links** có thể cung cấp các link điều hướng như self, next hoặc previous tùy response và cấu hình.

Collection rỗng vẫn là kết quả của association tập hợp. Khi không có item, phần **_embedded** có thể không xuất hiện hoặc không chứa phần tử; hãy xử lý collection rỗng thay vì coi đó là lỗi.

Nếu endpoint hỗ trợ phân trang, dùng các tham số mà API công bố và ưu tiên follow link next/previous trong response. Không tự giả định mọi association endpoint đều hỗ trợ mọi tham số sort hoặc page.

## 5. So sánh quan hệ đơn và quan hệ tập hợp

| Đặc điểm | Quan hệ đơn | Quan hệ tập hợp |
|---|---|---|
| Ví dụ JPA | @ManyToOne, @OneToOne | @OneToMany, @ManyToMany |
| Ví dụ endpoint | /orders/42/customer | /orders/42/lines |
| Kết quả | Một entity resource | Một collection resource |
| Cấu trúc HAL thường gặp | Thuộc tính entity và _links | _embedded, _links và có thể có page |
| Cách xử lý | Đọc một đối tượng hoặc theo link self | Duyệt danh sách, xử lý collection rỗng và phân trang |

Điểm quan trọng là cardinality của association quyết định dạng dữ liệu client cần xử lý. Không nên xử lý response của collection như một entity đơn hoặc ngược lại.

## 6. Gọi API bằng curl

Có thể kiểm tra luồng điều hướng bằng ba request:

~~~bash
# 1. Đọc đơn hàng và tìm association links
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42

# 2. Đọc khách hàng liên kết với đơn hàng
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42/customer

# 3. Đọc danh sách dòng hàng của đơn hàng
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42/lines
~~~

Khi kiểm tra, hãy đối chiếu **href** ở request đầu với URL được gọi ở request tiếp theo. Nếu server trả URL khác do cấu hình base path, reverse proxy hoặc custom association path, client nên dùng URL nhận được từ response.

## 7. Tùy chỉnh association path và relation

Có thể đổi đường dẫn và tên relation của association bằng **@RestResource**:

~~~java
@ManyToOne
@RestResource(path = "buyer", rel = "buyer")
private Customer customer;

@OneToMany(mappedBy = "order")
@RestResource(path = "items", rel = "items")
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi đó association link có thể được công bố dưới relation **buyer** và **items**, với path tương ứng:

- **/orders/42/buyer**
- **/orders/42/items**

Hãy kiểm tra link thực tế trong item resource sau khi thay đổi cấu hình. **path** điều khiển segment của endpoint; **rel** điều khiển tên relation xuất hiện trong HAL.

Nếu association được đánh dấu **@RestResource(exported = false)**, Spring Data REST không export association đó như endpoint công khai. Khi link không xuất hiện, cần kiểm tra cấu hình export của repository và association trước khi kết luận dữ liệu quan hệ bị thiếu.

## 8. Xử lý lỗi và các điểm cần kiểm tra

- **404 Not Found**: item resource không tồn tại hoặc URL association không được export/không hợp lệ.
- **401 Unauthorized / 403 Forbidden**: request chưa xác thực hoặc người gọi không có quyền đọc resource.
- **406 Not Acceptable**: media type client yêu cầu không được endpoint hỗ trợ; thử **Accept: application/hal+json** theo cấu hình ứng dụng.
- **Collection rỗng**: đây có thể là dữ liệu hợp lệ; kiểm tra **totalElements** nếu response có page metadata.
- **Không có association link**: kiểm tra repository có được export không, association có bị **exported = false** không và tên path/rel có được tùy chỉnh không.
- **Link trỏ đến host hoặc base path khác**: kiểm tra cấu hình base URI, proxy và cách ứng dụng tạo link; không sửa URL bằng cách đoán nếu server đã trả link.

GET chỉ đọc resource. Request GET đến association endpoint không thêm, xóa hoặc thay đổi quan hệ. Các thao tác cập nhật association thuộc những HTTP method và endpoint ghi tương ứng.

## 9. Quy trình thực hành

1. Khởi động ứng dụng và xác định base path của Spring Data REST.
2. Gọi **GET /orders/42** với **Accept: application/hal+json**.
3. Tìm relation của association đơn và collection trong **_links**.
4. Copy chính xác **href** của relation đơn và gọi GET; xác nhận response là một entity resource.
5. Copy **href** của relation tập hợp và gọi GET; xác nhận response là collection resource.
6. Thử với một đơn hàng không có dòng hàng để kiểm tra cách client xử lý collection rỗng.
7. Nếu đã cấu hình custom **path** hoặc **rel**, lặp lại việc khám phá link để xác nhận client vẫn điều hướng theo response.

## 10. Bài tập tự luyện

Cho một **PurchaseOrder** có một **Customer** và nhiều **OrderLine**:

1. Viết hai request GET để đọc customer và lines thông qua một purchase order.
2. Chỉ ra điểm khác nhau giữa response của hai request trong HAL JSON.
3. Giải thích vì sao client nên đọc **href** trong **_links** thay vì tự tạo URL.
4. Đổi association customer thành path **buyer** và relation **buyer**. Xác định link mới từ response của **GET /orders/42**.
5. Nêu các bước kiểm tra khi relation lines không xuất hiện trong **_links**.

**Ghi nhớ:** item resource giúp client khám phá các association link; GET association đơn trả về một resource, còn GET association tập hợp trả về một collection resource. Hãy dùng HAL links làm cơ chế điều hướng chính của client.
