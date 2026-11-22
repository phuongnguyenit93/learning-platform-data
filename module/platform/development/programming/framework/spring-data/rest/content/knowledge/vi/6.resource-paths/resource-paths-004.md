# Phân biệt đường dẫn URL và tên quan hệ liên kết (rel)

Trong Spring Data REST, **path** và **rel** là hai cấu hình khác nhau của một liên kết REST. **path** quyết định URL mà client gọi; **rel** quyết định tên quan hệ dùng để nhận diện liên kết trong tài liệu HAL. Chúng thường xuất hiện cạnh nhau trong annotation, nhưng không thay thế cho nhau.

Hãy hình dung một API có collection sản phẩm tại /api/catalog. Client nhìn thấy liên kết này trong HAL dưới tên products. Tên products là rel; URL /api/catalog là href được tạo từ path và base path của ứng dụng.

## 1. Phân biệt path và rel

| Thuộc tính | Vai trò | Ví dụ | Tác động |
|---|---|---|---|
| path | Xác định đoạn đường dẫn của tài nguyên hoặc truy vấn trong URL. | catalog, by-category | Thay đổi địa chỉ mà client dùng để truy cập tài nguyên. |
| rel | Đặt tên quan hệ cho liên kết trong HAL _links. | products, by-category | Thay đổi khóa mà client dùng để tìm liên kết trong tài liệu phản hồi. |

Ví dụ, với cấu hình:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Spring Data REST công bố collection resource tại URL dạng:

~~~text
/api/catalog
~~~

Trong tài liệu HAL, liên kết tới collection có quan hệ products:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api"
    },
    "products": {
      "href": "http://localhost:8080/api/catalog"
    }
  }
}
~~~

Trong ví dụ này:

- catalog là path dùng trong URL.
- products là collection rel xuất hiện dưới _links.
- Giá trị href là URL đầy đủ mà client có thể điều hướng tới.

Nếu đổi path thành inventory, URL collection sẽ đổi thành /api/inventory, trong khi rel vẫn có thể là products. Ngược lại, đổi collectionResourceRel thành items làm khóa liên kết thành _links.items, nhưng URL vẫn là /api/catalog.

## 2. Cấu hình path và collection rel ở cấp repository

@RepositoryRestResource cho phép cấu hình tên đường dẫn và tên quan hệ của collection resource:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

path xác định đoạn URL dành cho collection. Với base path là /api, collection nằm ở /api/catalog; item resource thường nằm dưới collection, ví dụ /api/catalog/42.

collectionResourceRel xác định quan hệ của collection trong HAL. Client tìm liên kết qua _links.products, rồi lấy URL từ thuộc tính href.

Có thể cấu hình hai giá trị độc lập:

~~~java
@RepositoryRestResource(
    path = "inventory",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Kết quả là URL collection /api/inventory, còn quan hệ HAL vẫn là products. Điều này hữu ích khi muốn URL phản ánh cách tổ chức endpoint trong hệ thống nhưng vẫn giữ một tên quan hệ có ý nghĩa với client.

Nếu bỏ qua các thuộc tính này, Spring Data REST sẽ áp dụng quy tắc mặc định để tạo đường dẫn và quan hệ từ repository hoặc domain type. Khi API được dùng bởi nhiều client, khai báo tường minh giúp hợp đồng URL và tên liên kết dễ dự đoán hơn.

## 3. Cấu hình path và rel cho truy vấn tìm kiếm

@RestResource cho phép đặt path và rel cho một phương thức repository được công bố. Ví dụ:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(
        path = "by-category",
        rel = "by-category"
    )
    List<Product> findByCategoryIgnoreCase(
        @Param("category") String category
    );
}
~~~

Truy vấn có path by-category, vì vậy URL tìm kiếm có dạng:

~~~http
GET /api/catalog/search/by-category?category=books
~~~

Ở đây:

- /api/catalog là collection path.
- /search là vùng tài nguyên tìm kiếm của repository.
- by-category trong URL là query path.
- by-category trong HAL là query rel.
- category=books là giá trị tham số truy vấn.

Khi client mở /api/catalog/search, Spring Data REST trả về các liên kết tới những truy vấn tìm kiếm đã công bố. Ví dụ, liên kết có thể có dạng:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/catalog/search"
    },
    "by-category": {
      "href": "http://localhost:8080/api/catalog/search/by-category{?category}",
      "templated": true
    }
  }
}
~~~

href chứa URI template vì truy vấn cần tham số category. Client đọc rel by-category, lấy template từ href, rồi điền giá trị tham số để gọi truy vấn.

Có thể đặt path và rel khác nhau:

~~~java
@RestResource(
    path = "category-filter",
    rel = "by-category"
)
List<Product> findByCategoryIgnoreCase(
    @Param("category") String category
);
~~~

Lúc này URL dùng /search/category-filter, còn khóa liên kết HAL vẫn là by-category. Client điều hướng theo rel mà không cần biết tên path cụ thể.

## 4. Cách client sử dụng rel và href

Trong HAL, _links là nơi chứa các liên kết. Mỗi khóa như products, search hoặc by-category là một link relation; bên trong là đối tượng mô tả liên kết, thường có href và có thể có templated.

Ví dụ JavaScript đọc collection link:

~~~javascript
const response = await fetch("/api");
const api = await response.json();

const productsUrl = api._links.products.href;
const productsResponse = await fetch(productsUrl);
const products = await productsResponse.json();
~~~

Ví dụ này tìm liên kết bằng rel products, rồi sử dụng href để gọi collection. Client không cần tự ghép /api/catalog.

Tương tự, để tìm truy vấn theo category, client có thể đọc liên kết search từ collection, mở search resource, rồi đọc rel by-category:

~~~javascript
const collection = await (await fetch("/api/catalog")).json();
const searchUrl = collection._links.search.href;

const search = await (await fetch(searchUrl)).json();
const categoryTemplate = search._links["by-category"].href;
~~~

Nếu href là URI template, client cần một thư viện hoặc đoạn mã xử lý URI template để thay thế tham số category trước khi gửi request. Không nên gửi nguyên chuỗi {?category} như một URL hoàn chỉnh.

## 5. Điều gì xảy ra khi thay đổi path hoặc rel?

Path và rel là hai phần của hợp đồng API, nên thay đổi từng phần có tác động khác nhau:

| Thay đổi | Điều thay đổi | Client có thể bị ảnh hưởng khi |
|---|---|---|
| Đổi path | URL trong href thay đổi. | Client lưu URL cũ hoặc tự ghép đường dẫn thay vì theo liên kết. |
| Đổi collectionResourceRel | Khóa liên kết collection trong _links thay đổi. | Client tìm collection bằng tên rel cũ, ví dụ _links.products. |
| Đổi @RestResource.path | URL truy vấn trong search resource thay đổi. | Client gọi trực tiếp URL tìm kiếm cũ. |
| Đổi @RestResource.rel | Khóa truy vấn trong _links của search resource thay đổi. | Client tìm truy vấn bằng rel cũ, ví dụ _links["by-category"]. |

Ví dụ, đổi:

~~~java
@RepositoryRestResource(
    path = "catalog",
    collectionResourceRel = "products"
)
~~~

thành:

~~~java
@RepositoryRestResource(
    path = "inventory",
    collectionResourceRel = "items"
)
~~~

sẽ làm URL collection đổi từ /api/catalog sang /api/inventory, đồng thời khóa HAL đổi từ _links.products sang _links.items.

Vì vậy, nếu API đã có client sử dụng, hãy xem thay đổi path và rel là thay đổi hợp đồng cần được thông báo và phối hợp. Khi cần đổi URL nhưng muốn client vẫn nhận diện cùng một loại tài nguyên, có thể giữ rel ổn định và chỉ đổi path; ngược lại, có thể giữ path và đổi rel nếu chủ đích thay đổi cách client nhận diện liên kết.

## 6. Quy tắc đặt tên dễ hiểu

- Dùng path ngắn, rõ nghĩa và phù hợp với cấu trúc URL, ví dụ catalog, orders, by-category.
- Dùng collectionResourceRel mô tả loại collection, ví dụ products, orders.
- Dùng rel cho truy vấn mô tả hành động hoặc ý nghĩa của liên kết, ví dụ by-category, recent, by-name.
- Giữ cách đặt tên nhất quán giữa các repository để client có thể khám phá API theo cùng một quy tắc.
- Dùng @Param để đặt tên tham số truy vấn rõ ràng, đặc biệt khi URL template được đưa cho client.
- Khai báo path và rel tường minh với các tài nguyên quan trọng để tránh phụ thuộc vào quy tắc mặc định.

Tên rel là định danh quan hệ của liên kết, không phải nhãn hiển thị bắt buộc cho người dùng cuối. Client dùng rel để tìm đúng liên kết trong tài liệu HAL; ứng dụng có thể quyết định cách trình bày nội dung đó trong giao diện.

## 7. Kiểm tra cấu hình sau khi chạy ứng dụng

Sau khi cấu hình repository, có thể kiểm tra bằng trình duyệt, curl hoặc REST client:

1. Mở endpoint gốc, ví dụ GET /api, rồi xác nhận _links.products.href trỏ tới /api/catalog.
2. Gọi GET /api/catalog và kiểm tra collection resource cùng các liên kết item.
3. Mở liên kết search từ collection resource.
4. Trong search resource, xác nhận _links.by-category.href trỏ tới query path /api/catalog/search/by-category.
5. Gọi truy vấn với tham số, ví dụ GET /api/catalog/search/by-category?category=books.
6. Thử thay đổi riêng path hoặc rel trong annotation để quan sát đúng phần URL hoặc khóa HAL thay đổi.

Khi kiểm tra, hãy đọc cả khóa rel lẫn giá trị href. Chỉ nhìn URL sẽ không cho biết client đang phải dùng tên quan hệ nào để khám phá liên kết; chỉ nhìn rel cũng không cho biết endpoint thực tế nằm ở đâu.

## 8. Những nhầm lẫn thường gặp

1. **Cho rằng path và rel là cùng một giá trị.** Chúng có thể trùng tên nhưng phục vụ hai mục đích riêng.
2. **Cho rằng đổi rel sẽ đổi URL.** Đổi rel làm thay đổi khóa liên kết trong HAL; URL do path và cấu hình base path quyết định.
3. **Cho rằng đổi path sẽ đổi khóa _links.** Path có thể đổi trong khi rel được giữ nguyên.
4. **Dùng rel như một URL.** Rel là tên quan hệ; URL truy cập nằm trong thuộc tính href.
5. **Hardcode URL ở client.** Client nên khám phá liên kết qua rel và sử dụng href để giảm phụ thuộc vào cấu trúc đường dẫn.
6. **Quên URI template của truy vấn.** Liên kết tìm kiếm có tham số thường có templated: true; client cần điền các tham số trước khi gửi request.

Hãy nhớ: path trả lời câu hỏi “gọi tài nguyên ở địa chỉ nào?”, còn rel trả lời câu hỏi “liên kết này đại diện cho quan hệ gì trong tài liệu HAL?”. Khi tách bạch hai khái niệm, bạn có thể tổ chức URL phù hợp với hệ thống và vẫn cung cấp các liên kết có ý nghĩa, ổn định cho client.
