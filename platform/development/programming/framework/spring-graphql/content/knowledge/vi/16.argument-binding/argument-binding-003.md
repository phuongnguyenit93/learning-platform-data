# `ArgumentValue` trong Spring for GraphQL

Khi nhận argument từ GraphQL request, có những trường hợp ứng dụng cần phân biệt ba trạng thái: client không gửi argument, client gửi argument với giá trị `null`, hoặc client gửi một giá trị cụ thể. Với tham số Java thông thường được bind bằng `@Argument`, hai trạng thái đầu thường cùng trở thành `null`. `ArgumentValue<T>` của Spring for GraphQL giữ lại thông tin argument có bị bỏ qua hay không, giúp resolver xử lý chính xác các mutation cập nhật từng phần.

Điều này đặc biệt hữu ích với thao tác PATCH. Nếu client không gửi trường `description`, server có thể giữ nguyên mô tả hiện tại. Nếu client gửi `description: null`, server có thể xóa mô tả. Nếu client gửi một chuỗi, server cập nhật sang giá trị mới.

## 1. Vấn đề: omitted khác với explicit null

Trong GraphQL, argument có kiểu nullable có thể được bỏ qua hoặc được gửi tường minh với giá trị `null`. Hai request sau không mang cùng ý nghĩa:

```graphql
mutation {
    updateProject(id: "project-01") {
        id
        description
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", description: null) {
        id
        description
    }
}
```

Request đầu tiên không gửi argument `description`. Request thứ hai gửi argument và chỉ rõ giá trị là `null`.

Trong một chức năng cập nhật từng phần, ta thường muốn quy ước:

| Trạng thái đầu vào | Ý nghĩa nghiệp vụ có thể chọn |
|---|---|
| Bỏ qua argument | Không thay đổi trường hiện tại. |
| Gửi `null` | Xóa giá trị hiện tại nếu trường cho phép rỗng. |
| Gửi giá trị | Gán giá trị mới. |

Nếu dùng tham số Java kiểu `String` hoặc `Optional<String>` với `@Argument`, resolver không thể phân biệt rõ hai trạng thái đầu theo cách này. `ArgumentValue<String>` giữ lại cả giá trị lẫn cờ cho biết argument có bị bỏ qua hay không.

## 2. `ArgumentValue<T>` là gì?

`ArgumentValue<T>` là một container trong Spring for GraphQL, thuộc package:

```java
import org.springframework.graphql.data.ArgumentValue;
```

Container giữ giá trị đã bind và trạng thái argument có bị bỏ qua hay không. Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
|---|---|
| `isOmitted()` | `true` nếu argument không được gửi; `false` nếu được gửi, kể cả khi giá trị là `null`. |
| `isPresent()` | `true` nếu có giá trị khác `null`. |
| `value()` | Trả về giá trị; có thể là `null`. |
| `asOptional()` | Chuyển giá trị thành `Optional`; không còn phân biệt omitted với explicit null. |
| `ArgumentValue.ofNullable(value)` | Tạo container cho argument đã được cung cấp, kể cả khi `value` là `null`. |
| `ArgumentValue.omitted()` | Tạo container biểu diễn argument bị bỏ qua. |

Ví dụ:

```java
ArgumentValue<String> omitted = ArgumentValue.omitted();
ArgumentValue<String> explicitNull = ArgumentValue.ofNullable(null);
ArgumentValue<String> provided = ArgumentValue.ofNullable("Spring GraphQL");
```

Kết quả:

| Container | `isOmitted()` | `isPresent()` | `value()` |
|---|---:|---:|---|
| `omitted` | `true` | `false` | `null` |
| `explicitNull` | `false` | `false` | `null` |
| `provided` | `false` | `true` | `"Spring GraphQL"` |

Điểm cần nhớ là `value() == null` chưa đủ để kết luận argument bị bỏ qua. Hãy kiểm tra `isOmitted()` trước, sau đó mới xử lý giá trị.

## 3. Dùng `ArgumentValue` làm tham số controller

`ArgumentValue` có thể được khai báo trực tiếp trên tham số handler. Có thể dùng nó thay cho `@Argument` nếu tên tham số Java khớp với tên argument GraphQL, hoặc kết hợp với `@Argument` để chỉ rõ tên argument.

SDL:

```graphql
type Project {
    id: ID!
    name: String
}

type Mutation {
    updateProject(id: ID!, name: String): Project
}
```

Controller:

```java
@Controller
class ProjectController {

    private final ProjectService projectService;

    ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @MutationMapping
    Project updateProject(
            @Argument("id") String id,
            @Argument("name") ArgumentValue<String> name) {

        if (name.isOmitted()) {
            return projectService.updateWithoutChangingName(id);
        }

        if (name.value() == null) {
            return projectService.clearName(id);
        }

        return projectService.rename(id, name.value());
    }
}
```

Resolver phân biệt ba trường hợp:

1. Không gửi `name`: gọi service giữ nguyên tên.
2. Gửi `name: null`: gọi service xóa tên nếu nghiệp vụ cho phép.
3. Gửi `name: "Tên mới"`: gọi service cập nhật tên.

Trong ví dụ, `name` được khai báo nullable trong SDL để client có thể bỏ qua hoặc gửi `null`. `id` là Non-null vì mutation cần định danh dự án. Nếu `name` được khai báo `String!`, GraphQL sẽ từ chối request thiếu hoặc gửi `null` trước khi gọi resolver; khi đó `ArgumentValue` không thể dùng để cho phép hai trường hợp ấy.

## 4. Dùng `ArgumentValue` trong input object

Với mutation có nhiều trường cần cập nhật, nên gom chúng vào một input object. `ArgumentValue` được hỗ trợ không chỉ ở tham số controller mà còn ở field bên trong object được bind từ `@Argument`, bao gồm field lồng nhau.

SDL:

```graphql
input ProjectPatchInput {
    name: String
    description: String
    website: String
}

type Mutation {
    patchProject(id: ID!, input: ProjectPatchInput!): Project!
}
```

Java record:

```java
public record ProjectPatchInput(
    ArgumentValue<String> name,
    ArgumentValue<String> description,
    ArgumentValue<String> website
) {}
```

Controller:

```java
@MutationMapping
Project patchProject(
        @Argument("id") String id,
        @Argument("input") ProjectPatchInput input) {

    return projectService.patch(id, input);
}
```

Trong service, xử lý từng field độc lập:

```java
Project patch(String id, ProjectPatchInput input) {
    Project project = findRequired(id);

    if (!input.name().isOmitted()) {
        if (input.name().value() == null) {
            project.clearName();
        }
        else {
            project.rename(input.name().value());
        }
    }

    if (!input.description().isOmitted()) {
        project.changeDescription(input.description().value());
    }

    if (!input.website().isOmitted()) {
        project.changeWebsite(input.website().value());
    }

    return projectRepository.save(project);
}
```

Đoạn mã trên minh họa chính sách cập nhật; các phương thức domain như `clearName`, `changeDescription` và `changeWebsite` cần được định nghĩa theo quy tắc nghiệp vụ của ứng dụng. Nếu `description` hoặc `website` không cho phép `null`, hãy kiểm tra và trả validation error thay vì gán `null`.

Vì `ArgumentValue` có thể xuất hiện trong cấu trúc object lồng nhau, ta cũng có thể dùng nó cho một field của input object con:

```java
public record ProjectSettingsPatch(
    ArgumentValue<Boolean> notificationsEnabled
) {}

public record ProjectPatchInput(
    ArgumentValue<String> name,
    ProjectSettingsPatch settings
) {}
```

Nếu `settings.notificationsEnabled` bị bỏ qua, giữ nguyên cấu hình hiện tại; nếu gửi `false`, tắt thông báo; nếu gửi `null`, ứng dụng có thể từ chối hoặc áp dụng quy tắc riêng. Việc phân biệt này đặc biệt quan trọng với Boolean vì `false` là giá trị hợp lệ, khác với `null`.

## 5. `ArgumentValue` cho toàn bộ input argument

Ngoài việc bọc từng field trong input object, có thể bọc cả argument của controller method:

```graphql
type Mutation {
    importProjects(input: ProjectImportInput): ImportResult!
}
```

```java
@MutationMapping
ImportResult importProjects(
        @Argument("input") ArgumentValue<ProjectImportInput> input) {

    if (input.isOmitted()) {
        return importService.importUsingDefaultInput();
    }

    if (input.value() == null) {
        return importService.rejectNullInput();
    }

    return importService.importProjects(input.value());
}
```

Ở đây `input` có thể bị bỏ qua, được gửi tường minh là `null`, hoặc chứa một `ProjectImportInput`. Nếu schema khai báo `input: ProjectImportInput!`, hai trường hợp đầu bị GraphQL từ chối trước khi resolver chạy. Chỉ khai báo nullable khi hợp đồng API thực sự cho phép các trạng thái đó.

## 6. Phân biệt `ArgumentValue`, `Optional` và tham số thông thường

Ba kiểu này không mang cùng một lượng thông tin:

| Kiểu tham số | Argument bị bỏ qua | Argument gửi `null` | Argument có giá trị |
|---|---|---|---|
| `String` với `@Argument` | Thường nhận `null` | Nhận `null` | Nhận giá trị |
| `Optional<String>` với `@Argument` | `Optional.empty()` | `Optional.empty()` | `Optional.of(value)` |
| `ArgumentValue<String>` | `isOmitted() == true` | `isOmitted() == false`, `value() == null` | `isOmitted() == false`, `value() != null` |

`Optional` biểu diễn có hoặc không có giá trị khác `null`; nó không giữ lại thông tin argument có được gửi hay không. `ArgumentValue` giữ thêm trạng thái omitted nên phù hợp khi logic cần phân biệt “không thay đổi” với “xóa giá trị”.

Không nên gọi `asOptional()` quá sớm nếu cần giữ sự khác biệt này, vì cả argument bị bỏ qua và argument gửi `null` đều trở thành `Optional.empty()`.

## 7. Ảnh hưởng của Non-null và default value trong SDL

`ArgumentValue` không thay thế quy tắc input coercion của GraphQL. Schema vẫn quyết định argument hoặc input field nào bắt buộc và có giá trị mặc định hay không.

| SDL | Khi client bỏ qua | Khi client gửi `null` |
|---|---|---|
| `name: String` | Có thể bỏ qua; `ArgumentValue` nhận biết omitted. | Được phép; `ArgumentValue` nhận biết explicit null. |
| `name: String!` | Request không hợp lệ nếu không có default value. | Request không hợp lệ. |
| `name: String = "Guest"` | GraphQL áp dụng giá trị mặc định. | `null` tường minh vẫn là giá trị được gửi nếu kiểu cho phép. |
| `name: String! = "Guest"` | GraphQL áp dụng giá trị mặc định. | `null` tường minh không hợp lệ. |

Nếu mục tiêu là phân biệt “không gửi” với “gửi null”, hãy cân nhắc không khai báo default value cho vị trí đó. Khi SDL cung cấp default, GraphQL áp dụng giá trị mặc định cho input bị bỏ qua; resolver sẽ làm việc với giá trị sau coercion thay vì coi việc bỏ qua như một lệnh PATCH độc lập.

Đối với input object, quy tắc tương tự áp dụng cho từng field. Field Non-null không thể bị bỏ qua hoặc gửi `null` nếu không có default value phù hợp. Hãy thiết kế SDL nullable cho những field thực sự cần hỗ trợ thao tác xóa hoặc không cập nhật.

## 8. Kiểm thử ba trạng thái với `GraphQlTester`

Khi kiểm thử `ArgumentValue`, không nên chỉ gửi một request có giá trị. Hãy kiểm tra riêng cả omitted, explicit null và giá trị thực.

Ví dụ ba GraphQL document:

```graphql
mutation {
    updateProject(id: "project-01") {
        id
        name
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", name: null) {
        id
        name
    }
}
```

```graphql
mutation {
    updateProject(id: "project-01", name: "Platform Team") {
        id
        name
    }
}
```

Trong test, xác minh service được gọi theo đúng ý nghĩa từng request:

| Request | Kỳ vọng |
|---|---|
| Không có `name` | Không thay đổi tên hiện tại. |
| `name: null` | Xóa tên nếu nghiệp vụ cho phép. |
| `name: "Platform Team"` | Cập nhật tên thành `Platform Team`. |

Có thể kiểm thử trực tiếp cờ omitted trong controller hoặc dùng Mockito `verify` để kiểm tra service nhận đúng lệnh. Với input object, hãy lặp lại ba trường hợp trên cho từng field quan trọng, đồng thời kiểm tra field không được gửi vẫn giữ nguyên dữ liệu cũ.

Nếu dùng variables, chú ý cách tạo map trong Java: `Map.of(...)` không cho phép giá trị `null`. Khi cần kiểm thử explicit null, dùng map có thể chứa null, ví dụ `HashMap`, hoặc viết literal `null` trong GraphQL document như các ví dụ trên.

## 9. Lưu ý khi áp dụng cho API cập nhật từng phần

`ArgumentValue` giúp giữ ý nghĩa đầu vào nhưng không tự quyết định quy tắc nghiệp vụ. Hãy quy định rõ cho từng field:

1. Bị bỏ qua có nghĩa là giữ nguyên, dùng default hay áp dụng một hành động khác?
2. `null` có hợp lệ để xóa dữ liệu không?
3. Giá trị cụ thể có cần chuẩn hóa hoặc validate không?
4. Nếu một field không hợp lệ, toàn bộ mutation thất bại hay các field hợp lệ vẫn được cập nhật?
5. Các thay đổi có cần nằm trong cùng transaction không?

Ví dụ, tên dự án có thể không được xóa nhưng mô tả có thể được xóa. Khi đó `name: null` phải tạo validation error, còn `description: null` có thể xóa mô tả. Không nên áp dụng một quy tắc null chung cho mọi field chỉ vì chúng cùng nằm trong một input object.

Nếu mutation thay đổi nhiều field, nên validate toàn bộ patch trước khi ghi dữ liệu để tránh cập nhật một phần ngoài ý muốn. Đặt logic đó trong service/domain layer; controller chỉ nhận và chuyển thông tin trạng thái từ `ArgumentValue`.

## 10. Lỗi thường gặp

**Chỉ kiểm tra `value() == null`.** Cả omitted và explicit null đều có thể trả về `null`. Hãy kiểm tra `isOmitted()` trước.

**Dùng `Optional` rồi mong biết client có gửi argument hay không.** `Optional.empty()` không phân biệt omitted với explicit null. Dùng `ArgumentValue` khi cần cả hai trạng thái.

**Khai báo field là Non-null nhưng muốn cho phép bỏ qua hoặc gửi null.** GraphQL từ chối request trước khi controller chạy. Đổi SDL sang nullable nếu hợp đồng cần cho phép các trạng thái này.

**Đặt default value rồi vẫn mong nhận biết omitted.** GraphQL áp dụng default khi input bị bỏ qua. Tránh default tại vị trí cần phân biệt omission với giá trị được cung cấp.

**Chuyển sang `Optional` quá sớm.** `asOptional()` làm mất khác biệt omitted và explicit null. Chỉ chuyển sau khi đã xử lý trạng thái omitted nếu logic cần phân biệt.

**Không xử lý `ArgumentValue` trong nested input.** Spring hỗ trợ container này bên trong cấu trúc object được bind từ `@Argument`; dùng nó cho những field PATCH cần giữ ba trạng thái.

**Để controller quyết định toàn bộ quy tắc cập nhật.** Hãy chuyển trạng thái đầu vào thành hành động domain rõ ràng và đặt quy tắc, validation, transaction trong service phù hợp.

## Kết luận

`ArgumentValue<T>` cho phép Spring for GraphQL phân biệt argument bị bỏ qua với argument được gửi tường minh là `null` hoặc có giá trị. Dùng `isOmitted()` để nhận biết trạng thái không gửi, `value()` để đọc giá trị và `isPresent()` khi cần xác nhận giá trị khác `null`. Container này có thể dùng trực tiếp trên tham số controller hoặc bên trong input object lồng nhau, rất hữu ích cho mutation PATCH. Hãy kết hợp với nullability và default value được thiết kế đúng trong SDL, rồi kiểm thử đủ ba trạng thái để API cập nhật có hành vi nhất quán.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: ArgumentValue](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL API — `ArgumentValue<T>`](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/ArgumentValue.html)
