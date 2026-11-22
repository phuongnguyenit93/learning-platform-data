# POST để bổ sung phần tử vào quan hệ tập hợp trong Spring Data REST

## Mục tiêu

Dùng HTTP **POST** trên association resource để thêm một tài nguyên đã tồn tại vào một quan hệ có nhiều phần tử, chẳng hạn thêm một **Tag** vào tập **tags** của một **Article**.

Sau bài này, bạn có thể:

- Nhận biết association resource của một thuộc tính kiểu tập hợp.
- Tìm đúng URL quan hệ từ HAL link của tài nguyên cha.
- Gửi URI của tài nguyên liên quan bằng **text/uri-list**.
- Đọc lại quan hệ để xác nhận thay đổi đã được lưu.

## 1. Hiểu đúng endpoint cần gọi

Spring Data REST có thể xuất bản association resource cho các thuộc tính quan hệ của entity. Với một thuộc tính tập hợp như **Set<Tag> tags** hoặc **List<Comment> comments**, endpoint association đại diện cho danh sách liên kết của một tài nguyên cha.

Ví dụ, tài nguyên bài viết:

~~~http
GET /articles/42
Accept: application/hal+json
~~~

có thể trả về HAL representation với các link tương tự:

~~~json
{
  "title": "Spring Data REST",
  "_links": {
    "self": {
      "href": "http://localhost:8080/articles/42"
    },
    "tags": {
      "href": "http://localhost:8080/articles/42/tags"
    }
  }
}
~~~

Link có relation **tags** trỏ tới association resource. Gọi **POST** vào URL này để bổ sung một tài nguyên vào quan hệ **tags** của bài viết số 42.

Đường dẫn trên là ví dụ theo cấu hình mặc định. Hãy dùng URL thực tế trong **_links** của response. **@RepositoryRestResource** có thể thay đổi đường dẫn repository; **@RestResource** trên thuộc tính quan hệ cũng có thể thay đổi relation hoặc path. Vì vậy không nên tự ghép URL khi response đã cung cấp link.

**Phân biệt hai loại endpoint:**

- **/tags** là collection resource của repository Tag, thường dùng để tạo hoặc liệt kê các Tag.
- **/articles/42/tags** là association resource của một Article cụ thể, dùng để quản lý các Tag được liên kết với Article đó.

**POST** lên association resource chỉ bổ sung liên kết. Nó không tạo mới entity đích.

## 2. Chuẩn bị entity và repository

Ví dụ dùng quan hệ nhiều-nhiều giữa **Article** và **Tag**. **Article.tags** là phía sở hữu quan hệ và lưu khóa liên kết trong bảng **article_tag**.

~~~java
@Entity
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @ManyToMany
    @JoinTable(
        name = "article_tag",
        joinColumns = @JoinColumn(name = "article_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new LinkedHashSet<>();

    // constructors, getters và setters
}
~~~

~~~java
@Entity
public class Tag {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany(mappedBy = "tags")
    private Set<Article> articles = new LinkedHashSet<>();

    // constructors, getters và setters
}
~~~

Các repository cần được Spring Data REST xuất bản để client có thể khám phá và tham chiếu tới tài nguyên:

~~~java
@RepositoryRestResource
public interface ArticleRepository
        extends JpaRepository<Article, Long> {
}
~~~

~~~java
@RepositoryRestResource
public interface TagRepository
        extends JpaRepository<Tag, Long> {
}
~~~

Tên package, cấu hình base path và annotation tùy ứng dụng. Điều quan trọng là tài nguyên cha có association link được xuất bản và URI của entity đích có thể được Spring Data REST phân giải.

Với JPA hai chiều, cần chú ý phía sở hữu quan hệ. Trong ví dụ này **Article.tags** sở hữu join table, nên cập nhật association này sẽ ghi quan hệ vào bảng liên kết. Nếu thuộc tính được gọi là association endpoint chỉ là phía inverse có **mappedBy**, việc chỉ thay đổi collection inverse có thể không cập nhật khóa ngoại hoặc bảng liên kết như mong muốn. Hãy thiết kế mapping và đồng bộ phía sở hữu cho đúng.

## 3. Đảm bảo hai tài nguyên đã tồn tại

Trước khi thêm quan hệ, cần có Article và Tag. Có thể tạo chúng qua collection resource của từng repository.

Ví dụ tạo Tag:

~~~http
POST /tags
Content-Type: application/json

{
  "name": "spring-data-rest"
}
~~~

Ví dụ tạo Article:

~~~http
POST /articles
Content-Type: application/json

{
  "title": "Làm việc với association resource"
}
~~~

Đọc **Location** trong response hoặc dùng link **self** để lấy URI thực tế của mỗi tài nguyên. Giả sử Article có URI **/articles/42** và Tag có URI **/tags/7**.

Nếu Tag đã tồn tại, không cần tạo lại. Chỉ cần dùng URI của Tag hiện có.

## 4. Gửi POST để thêm phần tử vào quan hệ

Gửi request tới association URL của Article:

~~~http
POST /articles/42/tags
Content-Type: text/uri-list
Accept: application/hal+json

http://localhost:8080/tags/7
~~~

Ví dụ bằng cURL:

~~~bash
curl -i -X POST "http://localhost:8080/articles/42/tags" \
  -H "Content-Type: text/uri-list" \
  -H "Accept: application/hal+json" \
  --data "http://localhost:8080/tags/7"
~~~

Các thành phần cần đúng:

1. **HTTP method:** **POST**, vì mục tiêu là thêm một phần tử vào collection association.
2. **Request URL:** association URL lấy từ link của tài nguyên cha, ở đây là **/articles/42/tags**.
3. **Content-Type:** **text/uri-list**.
4. **Request body:** URI tuyệt đối hoặc URI hợp lệ mà ứng dụng có thể phân giải tới tài nguyên đích. Body là URI thuần, không phải JSON object, không bọc URI trong dấu nháy.

Không gửi body dạng sau:

~~~json
{
  "id": 7,
  "name": "spring-data-rest"
}
~~~

Đây là dữ liệu entity, trong khi association endpoint cần tham chiếu tới tài nguyên đã tồn tại bằng URI. Cũng không dùng **Content-Type: application/json** cho body URI-list.

## 5. Kết quả và cách xác nhận

Khi request hợp lệ và association được cập nhật, Spring Data REST thường trả về:

~~~http
HTTP/1.1 204 No Content
~~~

**204** có nghĩa request đã được xử lý và response không có body. Không có JSON response không đồng nghĩa thao tác thất bại.

Hãy đọc lại tài nguyên cha hoặc association resource:

~~~http
GET /articles/42
Accept: application/hal+json
~~~

Kiểm tra link **tags** vẫn xuất hiện, sau đó đọc nội dung quan hệ:

~~~http
GET /articles/42/tags
Accept: application/hal+json
~~~

Kết quả cần thể hiện Tag có URI **/tags/7** trong danh sách liên kết của Article 42. Có thể kiểm tra thêm dữ liệu trong database nếu đang debug persistence.

Quy trình thực tế nên là:

1. Đọc tài nguyên cha để lấy association link.
2. Đọc hoặc tạo tài nguyên đích để có URI hợp lệ.
3. Gửi **POST** với **Content-Type: text/uri-list**.
4. Đọc lại association resource để xác nhận phần tử đã được thêm.

## 6. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| **404 Not Found** | Sai association URL, tài nguyên cha không tồn tại, hoặc URI trong body không trỏ tới tài nguyên đích có thể phân giải. |
| **415 Unsupported Media Type** | Thiếu hoặc đặt sai **Content-Type**; association request cần **text/uri-list**. |
| **400 Bad Request** | Body không phải URI hợp lệ hoặc URI không được phân tích đúng. |
| **405 Method Not Allowed** | Endpoint không hỗ trợ method này, hoặc thuộc tính không phải collection association được xuất bản. |
| Không thấy link quan hệ trong HAL | Kiểm tra repository/entity có được export không, relation có bị ẩn bằng **@RestResource(exported = false)** không và cấu hình relation/path. |
| Response thành công nhưng quan hệ không tồn tại trong database | Kiểm tra transaction, mapping JPA và phía sở hữu quan hệ; đặc biệt chú ý thuộc tính inverse có **mappedBy**. |
| Phần tử bị lặp | Kiểm tra kiểu collection (**List** hay **Set**), **equals**/**hashCode**, ràng buộc duy nhất và việc client gửi lại request. |

Khi debug, hãy kiểm tra theo thứ tự: URL association lấy từ HAL, URI tài nguyên đích, **Content-Type**, trạng thái HTTP, rồi mapping và trạng thái persistence.

## 7. Lưu ý khi thiết kế API và client

- **Không tạo entity đích bằng association POST.** Nếu Tag chưa tồn tại, tạo Tag qua repository resource trước rồi dùng URI của nó.
- **Dùng link do server cung cấp.** Cách này tránh phụ thuộc vào base path, repository path hoặc relation path đã được tùy chỉnh.
- **Tôn trọng kiểu collection.** **Set** phù hợp khi một quan hệ không nên có phần tử trùng; **List** có thể giữ thứ tự và có thể cho phép phần tử lặp tùy mapping.
- **Không mặc định POST là idempotent.** Nếu client timeout rồi gửi lại request, hãy đọc lại quan hệ trước khi quyết định gửi lại; đồng thời thiết kế collection và ràng buộc dữ liệu để xử lý phần tử trùng phù hợp.
- **Kiểm tra quyền truy cập.** Nếu ứng dụng dùng Spring Security, người gọi cần quyền đọc tài nguyên liên quan và quyền thay đổi quan hệ theo policy của ứng dụng.
- **Không nhầm với thao tác trên repository collection.** **POST /tags** tạo Tag; **POST /articles/42/tags** liên kết một Tag đã tồn tại với Article 42.

## Ghi nhớ

Để bổ sung một phần tử vào collection association trong Spring Data REST, hãy lấy association URL từ HAL link của tài nguyên cha, gửi **POST** tới URL đó với **Content-Type: text/uri-list**, và đặt URI của tài nguyên đích đã tồn tại trong body. Sau request, đọc lại association resource để xác nhận liên kết đã được lưu.