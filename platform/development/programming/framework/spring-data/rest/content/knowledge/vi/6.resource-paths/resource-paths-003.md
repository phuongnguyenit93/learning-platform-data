# Tùy chỉnh path, collectionResourceRel và itemResourceRel

Spring Data REST tự động xuất repository thành các tài nguyên REST. Với mỗi repository, ứng dụng có một đường dẫn để client truy cập collection và các item, đồng thời Spring Data REST tạo các liên kết theo chuẩn HAL để mô tả những tài nguyên có thể khám phá.

Có thể dùng **`@RepositoryRestResource`** để tùy chỉnh ba thành phần quan trọng:

- **`path`**: đoạn đường dẫn URL dùng để truy cập collection.
- **`collectionResourceRel`**: tên quan hệ (link relation, viết tắt là rel) của liên kết trỏ tới collection resource.
- **`itemResourceRel`**: tên quan hệ của các item resource được biểu diễn bên trong collection.

Ba thuộc tính này giải quyết hai việc khác nhau: **`path`** điều khiển URL, còn hai thuộc tính **`rel`** điều khiển tên quan hệ trong biểu diễn hypermedia.

## 1. @RepositoryRestResource dùng ở đâu?

**`@RepositoryRestResource`** thuộc package:

~~~java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Đặt annotation trên interface repository mà Spring Data REST quản lý. Ví dụ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Nếu không chỉ định thuộc tính tùy chỉnh, Spring Data REST tự suy ra mapping từ domain type và cấu hình quan hệ mặc định. Ví dụ với entity **`Employee`**, collection thường được xuất ở đường dẫn dạng **`/employees`**.

Khi cần kiểm soát tên URL hoặc tên liên kết hiển thị cho client, hãy khai báo rõ các thuộc tính tương ứng.

## 2. Tùy chỉnh path

**`path`** xác định path segment của collection resource. Đây là phần URL sau base path của Spring Data REST.

Ví dụ:

~~~java
@RepositoryRestResource(path = "staff-directory")
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Nếu ứng dụng không cấu hình base path toàn cục, collection resource có URL:

~~~http
GET /staff-directory
~~~

Mỗi item được truy cập qua URL dạng:

~~~http
GET /staff-directory/{id}
~~~

Nếu ứng dụng cấu hình base path, chẳng hạn **`/api`**, URL đầy đủ sẽ có dạng **`/api/staff-directory`**.

Lưu ý:

- **`path`** là một đoạn đường dẫn, ví dụ **`staff-directory`**.
- Đặt tên path ngắn, rõ nghĩa và ổn định để client có thể tích hợp lâu dài.
- Tránh trùng path giữa các repository cùng được xuất, vì mapping tài nguyên có thể xung đột.
- Đổi path sẽ làm thay đổi URL mà client đang gọi. Nếu API đã được sử dụng, cần cân nhắc tương thích ngược và kế hoạch chuyển đổi client.

## 3. Tùy chỉnh collectionResourceRel

**`collectionResourceRel`** xác định tên quan hệ của liên kết trỏ tới collection resource trong biểu diễn HAL.

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Khi client gửi **`GET /`** tới root của Spring Data REST, liên kết tới collection có thể xuất hiện như sau:

~~~json
{
  "_links": {
    "staff": {
      "href": "http://localhost:8080/staff-directory"
    }
  }
}
~~~

Trong ví dụ này:

- Client truy cập collection bằng URL **`/staff-directory`**.
- Tên liên kết HAL là **`staff`**.
- Thay đổi **`collectionResourceRel`** không tự thay đổi URL của collection.

Client HAL nên theo liên kết được mô tả trong **`_links`** thay vì tự ghép URL từ tên rel. Nhờ vậy, server có thể duy trì khả năng khám phá tài nguyên ngay cả khi cách tổ chức URL thay đổi.

## 4. Tùy chỉnh itemResourceRel

**`itemResourceRel`** xác định tên quan hệ trỏ tới một item resource bên trong collection representation.

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff",
    itemResourceRel = "staffMember"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Khi client gửi **`GET /staff-directory`**, phần **`_embedded`** của HAL có thể có dạng:

~~~json
{
  "_embedded": {
    "staffMember": [
      {
        "id": 1,
        "name": "An"
      },
      {
        "id": 2,
        "name": "Bình"
      }
    ]
  }
}
~~~

Tên **`staffMember`** mô tả quan hệ tới từng item trong collection. URL của item vẫn theo dạng **`/staff-directory/{id}`**; thuộc tính này không đổi cấu trúc URL.

Có thể chọn rel số ít, dễ đọc và phản ánh đúng loại tài nguyên, ví dụ **`person`**, **`order`** hoặc **`staffMember`**. Nên dùng cùng một quy ước đặt tên trong toàn bộ API.

## 5. Kết hợp cả ba thuộc tính

Trong thực tế, thường khai báo cả ba thuộc tính trên cùng một repository:

~~~java
package com.example.demo.repository;

import com.example.demo.entity.Employee;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "staff-directory",
    collectionResourceRel = "staff",
    itemResourceRel = "staffMember"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Với cấu hình này, các giá trị có ý nghĩa như sau:

| Thuộc tính | Giá trị | Tác dụng |
|---|---|---|
| **`path`** | **`staff-directory`** | URL collection là **`/staff-directory`** |
| **`collectionResourceRel`** | **`staff`** | Rel của liên kết tới collection |
| **`itemResourceRel`** | **`staffMember`** | Rel của item trong collection representation |

Có thể ghi nhớ bằng cách nhìn vào hai nơi khác nhau trong HAL:

- **`_links`** ở root của ứng dụng chứa liên kết collection với rel **`staff`**.
- **`_embedded`** của collection chứa các item với rel **`staffMember`**.

Tên rel là metadata hypermedia, không phải tên class Java, tên bảng cơ sở dữ liệu hoặc tên thuộc tính của entity.

## 6. Phân biệt path và rel

Ba thuộc tính có vai trò riêng. Không nên dùng thay thế cho nhau.

| Thay đổi | URL collection | Tên liên kết HAL |
|---|---|---|
| Chỉ đổi **`path`** | Thay đổi | Giữ mapping rel hiện tại |
| Chỉ đổi **`collectionResourceRel`** | Không đổi | Đổi rel của collection |
| Chỉ đổi **`itemResourceRel`** | Không đổi | Đổi rel của item trong collection |
| Đổi cả ba | Thay đổi theo path mới | Cập nhật cả hai rel |

Ví dụ, với:

~~~java
@RepositoryRestResource(
    path = "employees",
    collectionResourceRel = "team",
    itemResourceRel = "member"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Client truy cập collection qua **`/employees`**, tìm liên kết collection bằng rel **`team`** ở root, và đọc danh sách item dưới rel **`member`** trong collection representation.

Nếu chỉ muốn đổi URL mà vẫn giữ tên liên kết mặc định, chỉ cần cấu hình **`path`**. Nếu muốn giữ URL nhưng đổi cách client nhận diện tài nguyên, cấu hình các thuộc tính rel tương ứng.

## 7. Kiểm tra mapping sau khi cấu hình

Sau khi khởi động ứng dụng, kiểm tra bằng HTTP client, trình duyệt hoặc HAL Explorer.

**Bước 1 — Kiểm tra root resource**

~~~http
GET http://localhost:8080/
Accept: application/hal+json
~~~

Tìm liên kết có rel **`staff`** và xác nhận href trỏ tới **`/staff-directory`**.

**Bước 2 — Kiểm tra collection resource**

~~~http
GET http://localhost:8080/staff-directory
Accept: application/hal+json
~~~

Kiểm tra:

- Collection trả về thành công.
- Phần **`_embedded`** sử dụng rel **`staffMember`** cho các item.
- Các liên kết **`self`**, phân trang và điều hướng vẫn được tạo hợp lệ nếu có.

**Bước 3 — Kiểm tra item resource**

~~~http
GET http://localhost:8080/staff-directory/1
Accept: application/hal+json
~~~

Xác nhận item có thể được truy cập qua path mới. Giá trị ID phải tồn tại trong dữ liệu thử nghiệm.

Có thể dùng curl:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/staff-directory
curl -i -H "Accept: application/hal+json" http://localhost:8080/staff-directory/1
~~~

Nếu ứng dụng có base path, thay URL thử nghiệm bằng URL đầy đủ có thêm base path đó.

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| URL cũ trả về 404 sau khi đổi **`path`** | Collection đã được chuyển sang path mới | Kiểm tra path trong annotation và cập nhật client |
| Root vẫn có rel khác dự kiến | **`collectionResourceRel`** chưa được đặt trên đúng repository hoặc cấu hình chưa được nạp | Kiểm tra import, annotation và khởi động lại ứng dụng |
| **`_embedded`** có key khác mong đợi | **`itemResourceRel`** chưa được cấu hình hoặc đang dùng mapping mặc định | Kiểm tra annotation và response của collection |
| Đổi rel nhưng URL không đổi | Đây là hành vi đúng vì rel và path độc lập | Theo dõi href trong **`_links`** để biết URL thực tế |
| Ứng dụng không khởi động hoặc mapping bị xung đột | Hai repository có thể đang khai báo path không phù hợp | Đảm bảo mỗi collection resource có path riêng |

## 9. Lưu ý khi thiết kế API

- Chọn path có ý nghĩa nghiệp vụ, nhất quán về số ít/số nhiều và cách viết.
- Dùng rel mô tả loại tài nguyên để client hiểu nội dung liên kết mà không cần phụ thuộc tên class Java.
- Giữ rel ổn định vì client HAL có thể sử dụng rel để tìm tài nguyên.
- Kiểm tra cả root resource và collection representation sau mỗi thay đổi.
- Khi API đã có client bên ngoài, việc đổi path có thể phá vỡ URL cũ; hãy cân nhắc hỗ trợ chuyển tiếp hoặc phiên bản API.
- Chỉ dùng **`@RepositoryRestResource`** trên repository cần tùy chỉnh. Các thuộc tính này không thay thế cấu hình bảo mật, projection hay quy tắc xuất từng phương thức.

Tài liệu tham khảo chính thức:

- [RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
