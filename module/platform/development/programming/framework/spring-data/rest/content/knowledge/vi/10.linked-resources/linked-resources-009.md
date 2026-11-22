# Gỡ một phần tử khỏi quan hệ tập hợp bằng URI thành viên

Spring Data REST công bố quan hệ giữa các entity dưới dạng **association resource**. Với một association có nhiều thành viên, client có thể gỡ riêng một thành viên bằng cách gửi HTTP **DELETE** tới URI của association member. URI này chứa ID của entity thành viên ở đoạn cuối.

Ví dụ, một project có nhiều tag. Nếu muốn bỏ tag có ID 7 khỏi project có ID 42, request có dạng:

~~~http
DELETE /projects/42/tags/7
~~~

Thao tác này gỡ liên kết giữa project và tag. Nó không đồng nghĩa với việc xóa tag khỏi repository. Việc entity tag có bị xóa theo hay không còn phụ thuộc mapping JPA, cascade và quy tắc vòng đời entity của ứng dụng.

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận diện association collection resource và URI của từng member.
- Dùng DELETE với member ID trên đường dẫn để gỡ đúng một phần tử khỏi quan hệ tập hợp.
- Phân biệt xóa một liên kết, xóa toàn bộ association và xóa entity.
- Hiểu vai trò của HAL link, URI member và media type text/uri-list.
- Kiểm tra kết quả qua HTTP và persistence, đồng thời xử lý các vấn đề về mapping, quyền truy cập và tính nhất quán.

## 1. Mô hình ví dụ

Giả sử ứng dụng quản lý project và tag. Một project có thể gắn nhiều tag; một tag cũng có thể được dùng bởi nhiều project.

~~~java
@Entity
public class Project {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    private Set<Tag> tags = new HashSet<>();
}
~~~

Entity tag:

~~~java
@Entity
public class Tag {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
}
~~~

Repository được Spring Data REST công bố:

~~~java
@RepositoryRestResource(path = "projects")
public interface ProjectRepository
        extends JpaRepository<Project, Long> {
}

@RepositoryRestResource(path = "tags")
public interface TagRepository
        extends JpaRepository<Tag, Long> {
}
~~~

Với cấu hình mặc định, Spring Data REST tạo:

- Collection resource của project: /projects.
- Item resource của project: /projects/{projectId}.
- Association resource cho thuộc tính tags: /projects/{projectId}/tags.
- Item resource của tag: /tags/{tagId}.

Tên và path của association mặc định dựa trên tên thuộc tính quan hệ. Có thể tùy chỉnh bằng @RestResource trên thuộc tính đó.

## 2. Khám phá association và member URI

Client nên bắt đầu từ item resource của project:

~~~http
GET /projects/42
Accept: application/hal+json
~~~

Representation HAL có thể chứa link đến association collection:

~~~json
{
  "name": "Learning Platform",
  "_links": {
    "self": {
      "href": "http://localhost:8080/projects/42"
    },
    "tags": {
      "href": "http://localhost:8080/projects/42/tags"
    }
  }
}
~~~

Client theo link tags để đọc các tag đang gắn với project:

~~~http
GET /projects/42/tags
Accept: application/hal+json
~~~

Kết quả có thể biểu diễn collection với các item link đến từng tag:

~~~json
{
  "_embedded": {
    "tags": [
      {
        "name": "java",
        "_links": {
          "self": {
            "href": "http://localhost:8080/tags/7"
          }
        }
      },
      {
        "name": "spring",
        "_links": {
          "self": {
            "href": "http://localhost:8080/tags/8"
          }
        }
      }
    ]
  }
}
~~~

Trong ví dụ này:

- Association collection URI là /projects/42/tags.
- Member URI của tag java là /tags/7.
- ID của member cần gỡ là 7.

Client có thể dùng link self của member để nhận diện đúng tài nguyên liên quan. Endpoint xóa member của Spring Data REST sử dụng ID của member làm path segment cuối cùng.

## 3. DELETE một member cụ thể

Để gỡ tag có ID 7 khỏi project 42, gọi:

~~~http
DELETE /projects/42/tags/7 HTTP/1.1
Accept: application/hal+json
~~~

Hoặc dùng curl:

~~~bash
curl -i -X DELETE http://localhost:8080/projects/42/tags/7
~~~

Đường dẫn có ba phần sau base path:

| Phần | Ý nghĩa |
| --- | --- |
| /projects/42 | Item resource của project cha |
| /tags | Association collection resource |
| /7 | ID của member cần gỡ khỏi association |

Controller của Spring Data REST có route member-specific theo dạng:

~~~text
/{repository}/{id}/{property}/{propertyId}
~~~

Trong đó propertyId là ID của entity thành viên trong association. Với ví dụ trên, route được phân giải thành:

~~~text
/projects/42/tags/7
~~~

Request DELETE này không cần JSON body và không cần gửi text/uri-list. URI của member được thể hiện bằng đoạn path chứa ID ở cuối URL.

Khi thao tác thành công, response thường là 204 No Content. Client không nên phụ thuộc vào response body; hãy đọc lại association để xác nhận thành viên đã được gỡ.

## 4. Phân biệt ba loại thao tác

Đây là phần cần nắm rõ để tránh xóa nhầm dữ liệu:

| Ý định | Endpoint | Tác động |
| --- | --- | --- |
| Gỡ một member khỏi collection association | DELETE /projects/42/tags/7 | Bỏ liên kết tag 7 khỏi project 42 |
| Thao tác trên association resource ở cấp thuộc tính | DELETE /projects/42/tags | Nhắm tới toàn bộ association property; không phải route member-specific |
| Xóa entity tag | DELETE /tags/7 | Xóa tài nguyên tag 7 khỏi repository nếu được phép |

Với collection association, hãy dùng route có thêm member ID để gỡ riêng một phần tử. Không dùng DELETE ở association collection URI với kỳ vọng chỉ xóa một thành viên.

DELETE trên item resource /tags/7 có ý nghĩa khác hoàn toàn: nó yêu cầu xóa entity tag khỏi repository. Nếu tag đang được nhiều project tham chiếu, hành động đó có thể ảnh hưởng nhiều quan hệ và bị ràng buộc bởi khóa ngoại hoặc cascade.

## 5. DELETE khác POST và PUT trên association như thế nào?

Spring Data REST hỗ trợ các thao tác khác nhau trên association resource:

| Method | Mục đích | Request body / media type |
| --- | --- | --- |
| GET | Đọc trạng thái association | Accept: application/hal+json hoặc application/json |
| POST | Thêm một member vào collection association | Content-Type: text/uri-list |
| PUT | Gắn URI member vào association; với collection, dùng để gửi tập URI cần liên kết theo hợp đồng của endpoint | Content-Type: text/uri-list |
| DELETE | Gỡ association hoặc một member cụ thể qua member-specific URI | Không cần body cho thao tác gỡ một member |

Ví dụ thêm tag 9 vào project 42:

~~~http
POST /projects/42/tags HTTP/1.1
Content-Type: text/uri-list

http://localhost:8080/tags/9
~~~

Ví dụ curl:

~~~bash
curl -i -X POST -H "Content-Type: text/uri-list" --data "http://localhost:8080/tags/9" http://localhost:8080/projects/42/tags
~~~

POST gửi URI của entity muốn thêm trong body. DELETE member-specific đưa ID của entity cần gỡ vào path. Hai giao thức này không hoán đổi cho nhau.

Nếu cần thay toàn bộ liên kết collection, hãy xem xét semantics của PUT và gửi danh sách URI theo đúng hợp đồng của phiên bản Spring Data REST đang chạy. Đừng dùng PUT chỉ để gỡ một phần tử nếu mục tiêu thực tế là xóa một member đơn lẻ.

## 6. Dùng member URI như thế nào?

Trong HAL, member thường có link self trỏ tới URI của entity thành viên, ví dụ:

~~~text
http://localhost:8080/tags/7
~~~

URI này cho client biết chính xác member cần tác động. Với route member-specific của Spring Data REST, ID cuối cùng (7) được đặt sau association path:

~~~text
DELETE /projects/42/tags/7
~~~

Không gửi toàn bộ URL http://localhost:8080/tags/7 trong request body của DELETE. Cũng không gửi một JSON object kiểu:

~~~json
{
  "uri": "http://localhost:8080/tags/7"
}
~~~

Hợp đồng member-specific DELETE là URI path có propertyId. URI của member được dùng để khám phá/nhận diện tài nguyên, còn ID được đặt vào đoạn path cuối cùng theo route của controller.

Nếu ứng dụng dùng base path, reverse proxy hoặc repository path tùy chỉnh, hãy lấy association link từ HAL response rồi tạo request theo route thực tế. Nếu ID có ký tự cần URL encoding hoặc ứng dụng dùng cơ chế ID tùy chỉnh, hãy kiểm tra URI mà server công bố và hành vi của phiên bản Spring Data REST đang dùng.

## 7. Tùy chỉnh association path

Tên association mặc định lấy từ tên thuộc tính. Có thể tùy chỉnh path bằng @RestResource:

~~~java
@ManyToMany
@RestResource(path = "labels", rel = "labels")
private Set<Tag> tags = new HashSet<>();
~~~

Khi đó association collection có path:

~~~text
/projects/42/labels
~~~

Member-specific DELETE tương ứng:

~~~http
DELETE /projects/42/labels/7
~~~

path điều khiển đoạn URL của association. rel điều khiển tên link relation trong HAL. Nếu đã đổi path, client phải dùng href mới mà server trả về; không tiếp tục ghép URL bằng tên field Java cũ.

## 8. Gỡ liên kết không đồng nghĩa xóa entity

Khi gọi:

~~~http
DELETE /projects/42/tags/7
~~~

ý nghĩa của thao tác là xóa quan hệ giữa project 42 và tag 7 khỏi association collection. Entity tag 7 vẫn có thể tồn tại và tiếp tục được project khác sử dụng.

Có thể kiểm tra riêng hai tài nguyên sau thao tác:

~~~http
GET /projects/42/tags
~~~

Tag 7 không còn xuất hiện trong association của project 42.

~~~http
GET /tags/7
~~~

Tag 7 vẫn có thể được đọc qua repository riêng.

Tuy nhiên, trạng thái persistence cuối cùng còn phụ thuộc mapping của domain model:

- Với @ManyToMany, gỡ member thường loại bỏ liên kết trong join table; entity được tham chiếu không nên bị xóa chỉ vì bị gỡ khỏi một collection.
- Với @OneToMany, việc gỡ child khỏi collection có thể tương tác với orphanRemoval = true.
- Cascade remove và các ràng buộc database có thể ảnh hưởng vòng đời entity.
- Nếu quan hệ hai chiều, cần duy trì nhất quán cả hai phía của object graph.

Không suy ra entity chắc chắn còn tồn tại chỉ từ HTTP status của association DELETE. Hãy kiểm tra mapping JPA và đọc lại item resource của member nếu cần bảo đảm entity không bị xóa.

## 9. Lưu ý về owning side của JPA

Trong quan hệ hai chiều, JPA chỉ ghi thay đổi quan hệ dựa trên owning side.

Ví dụ:

~~~java
@Entity
public class Project {

    @ManyToMany
    @JoinTable(
        name = "project_tag",
        joinColumns = @JoinColumn(name = "project_id"),
        inverseJoinColumns = @JoinColumn(name = "tag_id")
    )
    private Set<Tag> tags = new HashSet<>();
}

@Entity
public class Tag {

    @ManyToMany(mappedBy = "tags")
    private Set<Project> projects = new HashSet<>();
}
~~~

Ở ví dụ này, Project.tags là owning side; Tag.projects là inverse side do có mappedBy.

Khi gỡ tag khỏi project, cần bảo đảm thay đổi được thực hiện trên owning side. Nếu client thao tác association được công bố từ phía inverse side, hãy kiểm thử kỹ việc lưu join table và cân nhắc cập nhật hai phía bằng logic domain phù hợp.

Một helper method có thể giữ object graph nhất quán:

~~~java
public void removeTag(Tag tag) {
    tags.remove(tag);
    tag.getProjects().remove(this);
}
~~~

Ví dụ này minh họa cách giữ hai collection đồng bộ trong domain logic. Không mặc định rằng mọi mapping đều cần đúng helper này; hãy điều chỉnh theo owning side, cascade và thiết kế entity của ứng dụng.

## 10. Quan hệ bắt buộc và lỗi thường gặp

Spring Data REST mô tả DELETE association là thao tác unbind. Nếu association là quan hệ đơn trị không cho phép null hoặc không thể gỡ, DELETE có thể trả 405 Method Not Allowed.

Với collection association, thao tác gỡ một member dùng member-specific URI. Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| 404 Not Found | Parent item không tồn tại, association path sai hoặc member URI/ID không hợp lệ | Theo link HAL, kiểm tra parent ID, path và member ID |
| 405 Method Not Allowed | Endpoint không hỗ trợ DELETE, association không thể unbind hoặc route không đúng | Kiểm tra mapping, repository exposure và route có propertyId |
| Member vẫn xuất hiện sau DELETE | Thay đổi không được persist, thao tác trên inverse side hoặc transaction rollback | Đọc lại association và kiểm tra owning side, log persistence |
| Entity member bị xóa ngoài dự kiến | Cascade hoặc orphan removal tác động đến vòng đời entity | Kiểm tra cascade, orphanRemoval và mapping |
| Gỡ nhầm member | Client ghép ID sai hoặc dùng ID từ collection khác | Dùng member self link và xác nhận member thuộc đúng association |
| Link collection không tìm thấy | Repository/association không được công bố hoặc path đã tùy chỉnh | Đọc item resource và theo link do server trả về |

HTTP status cụ thể còn phụ thuộc cấu hình, exception handler, repository module và phiên bản Spring Data REST.

## 11. Kiểm thử thao tác gỡ member

Một kiểm thử nên xác nhận cả association và entity độc lập:

1. Tạo project 42 có các tag 7 và 8.
2. Đọc /projects/42 và theo link association tags.
3. Xác nhận collection chứa URI của tag 7 và tag 8.
4. Gửi DELETE /projects/42/tags/7.
5. Xác nhận response thành công, thường là 204 No Content.
6. Đọc lại /projects/42/tags; tag 7 phải không còn trong collection, tag 8 vẫn còn.
7. Đọc /tags/7; xác nhận entity còn tồn tại nếu mapping không quy định xóa orphan hoặc cascade.
8. Đọc /projects/42; xác nhận các link và representation khác vẫn đúng.
9. Kiểm tra join table hoặc dữ liệu lưu trữ tương ứng nếu cần xác nhận persistence.
10. Thử gỡ member không thuộc association và ghi nhận hành vi của đúng phiên bản ứng dụng.

Ví dụ kiểm tra trước/sau:

~~~text
Before:
Project 42 -> tags [7, 8]

Request:
DELETE /projects/42/tags/7

After:
Project 42 -> tags [8]
Tag 7 -> still exists in /tags/7 (when no lifecycle rule deletes it)
~~~

Không chỉ kiểm tra collection JSON ở một lần đọc. Nếu ứng dụng có cache, transaction hoặc read replica, hãy đọc lại sau khi transaction hoàn tất và dùng nguồn dữ liệu có thể xác nhận trạng thái đã commit.

## 12. Bảo mật và tính nhất quán

DELETE association là thao tác ghi dữ liệu. API cần kiểm soát quyền trên cả parent resource và association.

- Người gọi phải có quyền sửa quan hệ của project 42.
- Không cho phép suy ra quyền truy cập chỉ từ việc client biết tag ID.
- Kiểm tra tenant/owner của cả parent và member để tránh gỡ quan hệ chéo tenant.
- Validate rằng member thuộc đúng association trước khi thay đổi.
- Xem xét optimistic locking hoặc xử lý xung đột khi nhiều client đồng thời sửa cùng collection.
- Ghi audit nếu nghiệp vụ cần biết ai đã gỡ liên kết nào và khi nào.

Việc member tồn tại ở repository riêng không có nghĩa người gọi được phép gắn hoặc gỡ nó khỏi mọi parent resource.

## 13. Checklist nhanh

- [ ] Đã lấy association href từ HAL representation của parent.
- [ ] Đã lấy đúng member URI từ association collection.
- [ ] Đã xác định member ID để dùng làm path segment cuối.
- [ ] Request dùng DELETE /{repository}/{parentId}/{property}/{propertyId}.
- [ ] Không gửi JSON body hoặc text/uri-list body cho member-specific DELETE.
- [ ] Đã phân biệt gỡ association member với xóa entity member.
- [ ] Đã kiểm tra @RestResource(path = "...") nếu association path được tùy chỉnh.
- [ ] Đã kiểm tra owning side, cascade và orphan removal của JPA.
- [ ] Đã kiểm tra quyền sửa association và quyền truy cập member.
- [ ] Đã đọc lại association sau thao tác và xác nhận member được gỡ.

## 14. Ghi nhớ

Để gỡ riêng một phần tử khỏi collection association, dùng URI member-specific:

~~~http
DELETE /projects/42/tags/7
~~~

- /projects/42/tags là association collection của project.
- /7 là ID của member cần gỡ.
- Request DELETE không cần body; ID nằm trong URI.
- POST và PUT dùng text/uri-list để thêm hoặc gắn URI; đó là hợp đồng khác với member-specific DELETE.
- Gỡ liên kết không tự động có nghĩa xóa entity. Hãy kiểm tra mapping, cascade, orphan removal và owning side.

## Tài liệu tham khảo

- Spring Data REST Reference — Repository resources, The Association Resource: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST source — RepositoryPropertyReferenceController: https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryPropertyReferenceController.java
- Spring Data REST Reference — Customizing Spring Data REST: https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr.html
- Jakarta Persistence Specification — Entity Relationships and owning side: https://jakarta.ee/specifications/persistence/
