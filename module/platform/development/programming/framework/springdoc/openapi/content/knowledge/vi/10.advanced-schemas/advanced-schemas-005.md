# Quan hệ đệ quy, vòng tham chiếu và mô hình cây

Nhiều API biểu diễn dữ liệu có cấu trúc phân cấp như danh mục sản phẩm, thư mục, sơ đồ tổ chức, nhóm quyền hoặc bình luận trả lời lẫn nhau. Các cấu trúc này thường có quan hệ cha-con và có thể lồng nhau ở nhiều cấp. Trong Java, chúng thường được mô hình hóa bằng một lớp có thuộc tính tham chiếu đến chính kiểu của nó hoặc tham chiếu qua một kiểu khác. Trong OpenAPI, schema tương ứng sử dụng **$ref** để tham chiếu lại component đã định nghĩa.

Với **springdoc-openapi**, schema đệ quy có thể được sinh từ DTO Java và được biểu diễn bằng tham chiếu trong **components.schemas**. Tuy nhiên, cần phân biệt hai khái niệm:

- **Đệ quy của schema:** cấu trúc dữ liệu có thể lồng nhau ở nhiều cấp theo cùng một quy tắc.
- **Vòng tham chiếu của object runtime:** các object Java trỏ ngược về nhau, khiến serializer có thể đi vòng lặp vô hạn nếu không xử lý.

Một schema đệ quy hợp lệ không đồng nghĩa response JSON được phép chứa vòng lặp object. JSON là cấu trúc cây hữu hạn; muốn truyền quan hệ đồ thị có chu trình, API cần quy ước biểu diễn bằng ID hoặc tham chiếu tường minh.

## 1. Đệ quy trong mô hình dữ liệu

Một kiểu dữ liệu có tính đệ quy khi một thuộc tính của nó có thể chứa một giá trị cùng kiểu, trực tiếp hoặc thông qua collection. Ví dụ, một danh mục có thể chứa các danh mục con:

~~~java
import java.util.List;

public record CategoryNode(
    String id,
    String name,
    List<CategoryNode> children
) {}
~~~

Mỗi **CategoryNode** có danh sách **children**, và mỗi phần tử trong danh sách cũng là **CategoryNode**. Do đó, một danh mục có thể có con, cháu và các cấp sâu hơn mà không cần định nghĩa một lớp Java riêng cho từng cấp.

Ví dụ dữ liệu JSON hữu hạn:

~~~json
{
  "id": "root",
  "name": "Thiết bị",
  "children": [
    {
      "id": "laptop",
      "name": "Máy tính xách tay",
      "children": [
        {
          "id": "gaming",
          "name": "Laptop chơi game",
          "children": []
        }
      ]
    }
  ]
}
~~~

Mỗi nhánh có thể tiếp tục lồng nhau. Dữ liệu vẫn là JSON hợp lệ vì cây cụ thể có điểm kết thúc; đệ quy chỉ mô tả khả năng cấu trúc có độ sâu thay đổi.

Các tình huống thường dùng mô hình đệ quy:

| Nghiệp vụ | Quan hệ | Ví dụ |
| --- | --- | --- |
| Danh mục | Một nút có nhiều nút con | Danh mục sản phẩm và danh mục con |
| Thư mục | Một thư mục chứa thư mục khác | Cây thư mục lưu trữ |
| Bình luận | Một bình luận có nhiều câu trả lời | Chủ đề thảo luận |
| Tổ chức | Một đơn vị quản lý đơn vị cấp dưới | Phòng ban và nhóm |
| Menu | Một mục có các mục con | Menu nhiều cấp |

Trước khi thiết kế schema, cần xác định dữ liệu thực sự là cây, rừng nhiều cây, hay đồ thị có quan hệ dùng chung và chu trình. Cách biểu diễn phù hợp sẽ khác nhau.

## 2. Biểu diễn schema đệ quy bằng $ref

Trong OpenAPI, có thể định nghĩa một schema trong **components.schemas**, sau đó tham chiếu lại chính schema đó ở thuộc tính con.

Ví dụ schema cho CategoryNode:

~~~yaml
components:
  schemas:
    CategoryNode:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: string
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/CategoryNode'
~~~

Thuộc tính **children.items.$ref** trỏ lại **CategoryNode**. Tham chiếu này cho phép schema mô tả cấu trúc có độ sâu tùy ý mà không cần sao chép định nghĩa ở từng cấp.

Một response sử dụng schema:

~~~yaml
paths:
  /api/categories/tree:
    get:
      summary: Lấy cây danh mục
      responses:
        '200':
          description: Cây danh mục
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CategoryNode'
~~~

Tham chiếu **$ref** là cơ chế tái sử dụng schema trong tài liệu OpenAPI. Nó không phải cú pháp đặc biệt của JSON response. Client nhận JSON lồng nhau bình thường; công cụ đọc OpenAPI lần theo tham chiếu để hiểu cấu trúc.

Một component có thể tham chiếu chính nó hoặc tham chiếu một component khác tạo thành chuỗi tham chiếu. OpenAPI cho phép schema tham chiếu đệ quy. Điều quan trọng là mọi tham chiếu phải trỏ đến component tồn tại và cấu trúc cuối cùng phải mô tả được dữ liệu hữu hạn mà server phát ra.

## 3. Springdoc suy luận schema đệ quy từ DTO

Springdoc phân tích kiểu trả về, DTO, annotation Jackson và annotation OpenAPI để xây dựng schema. Với DTO tự tham chiếu như **CategoryNode**, springdoc có thể tạo component schema và dùng **$ref** cho thuộc tính cùng kiểu.

Ví dụ controller:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.media.Content;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CategoryController {

    private final CategoryService categoryService;

    CategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @Operation(
        summary = "Lấy cây danh mục",
        description = "Trả về một nút gốc cùng các danh mục con lồng nhau."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Cây danh mục",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CategoryNode.class)
        )
    )
    @GetMapping("/api/categories/tree")
    CategoryNode getTree() {
        return categoryService.loadTree();
    }
}
~~~

DTO:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CategoryNode", description = "Một nút trong cây danh mục")
public record CategoryNode(
    @Schema(description = "Mã danh mục", example = "laptop")
    String id,

    @Schema(description = "Tên danh mục", example = "Máy tính xách tay")
    String name,

    @Schema(description = "Các danh mục con")
    List<CategoryNode> children
) {}
~~~

Với cấu trúc này, springdoc thường tạo một component **CategoryNode** và để **children.items** tham chiếu component đó. Annotation **@Schema(implementation = CategoryNode.class)** ở response làm rõ kiểu schema gốc; nó không cần lặp định nghĩa cho từng cấp.

Không nên cố khai báo một lớp Java riêng như **CategoryLevel1**, **CategoryLevel2**, **CategoryLevel3** chỉ để mô tả độ sâu. Cách đó giới hạn cấu trúc và làm schema khó bảo trì khi nghiệp vụ cho phép cây sâu hơn.

## 4. Tham chiếu trực tiếp, gián tiếp và nhiều component

Đệ quy không nhất thiết là một lớp tham chiếu chính nó. Hai hoặc nhiều kiểu có thể tham chiếu qua lại.

Ví dụ nhân viên có người quản lý là một nhân viên khác, và có danh sách nhân viên báo cáo trực tiếp:

~~~java
import java.util.List;

public record EmployeeView(
    String id,
    String name,
    EmployeeView manager,
    List<EmployeeView> reports
) {}
~~~

Schema có dạng:

~~~yaml
components:
  schemas:
    EmployeeView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        manager:
          $ref: '#/components/schemas/EmployeeView'
        reports:
          type: array
          items:
            $ref: '#/components/schemas/EmployeeView'
~~~

Trong trường hợp hai kiểu khác nhau tham chiếu qua lại, ví dụ **DepartmentView** chứa **EmployeeView** và **EmployeeView** lại chứa **DepartmentView**, OpenAPI có thể biểu diễn bằng hai component:

~~~yaml
components:
  schemas:
    DepartmentView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        manager:
          $ref: '#/components/schemas/EmployeeView'

    EmployeeView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        department:
          $ref: '#/components/schemas/DepartmentView'
~~~

Đây là vòng tham chiếu giữa các định nghĩa schema. Công cụ xử lý OpenAPI cần hỗ trợ tham chiếu đệ quy để hiển thị hoặc sinh client. Khi dùng các công cụ có giới hạn với schema vòng, có thể cần thiết kế DTO phẳng hơn hoặc biểu diễn quan hệ bằng ID.

## 5. Phân biệt cây, đồ thị và vòng tham chiếu object

Một cây có các đặc điểm:

- Có một nút gốc cho mỗi cây.
- Mỗi nút con có một cha trong cây đó.
- Không có chu trình.
- Có một đường đi duy nhất từ nút gốc đến mỗi nút.

Một đồ thị có thể có nhiều quan hệ giữa các nút, một nút được nhiều nút khác tham chiếu hoặc có chu trình. Ví dụ, một nhân viên có thể tham gia nhiều dự án; một dự án có nhiều thành viên. Đây là quan hệ nhiều-nhiều, không nhất thiết là cây.

Sự khác biệt quan trọng:

| Khái niệm | Cấu trúc | Cách biểu diễn thường phù hợp |
| --- | --- | --- |
| Schema đệ quy | Một kiểu có thể lồng nhau nhiều cấp | Component tự tham chiếu bằng **$ref** |
| JSON tree | Dữ liệu lồng nhau hữu hạn | Object và array lồng nhau |
| Object graph có chu trình | Các object Java trỏ ngược hoặc trỏ vòng | DTO có ID, tham chiếu tường minh hoặc cơ chế identity |
| Đồ thị có cạnh | Nhiều nút và quan hệ nối giữa chúng | Danh sách nodes và edges dùng ID |

Ví dụ một object Java có vòng tham chiếu:

~~~java
class Category {
    public String id;
    public Category parent;
    public List<Category> children;
}
~~~

Nếu **parent.children** chứa chính object con và **child.parent** lại trỏ về object cha, object graph trong bộ nhớ có chu trình. Jackson tuần tự hóa theo cách duyệt thuộc tính có thể đi từ cha xuống con rồi quay lại cha, tiếp tục lặp. Kết quả có thể là lỗi lồng quá sâu hoặc lỗi do vòng lặp, thay vì một JSON hữu hạn.

Schema OpenAPI tự tham chiếu không tạo ra chu trình runtime. Vòng lặp xuất hiện do object graph thực tế và quy tắc serialization.

## 6. Thiết kế DTO cây để tránh vòng lặp JSON

Với API trả cây phân cấp, cách đơn giản và dễ kiểm soát là tạo DTO có một chiều từ cha xuống con. Không đưa tham chiếu ngược về cha vào từng node; nếu client cần biết cha, có thể gửi **parentId**.

~~~java
public record CategoryNodeView(
    String id,
    String parentId,
    String name,
    List<CategoryNodeView> children
) {}
~~~

JSON:

~~~json
{
  "id": "root",
  "parentId": null,
  "name": "Thiết bị",
  "children": [
    {
      "id": "laptop",
      "parentId": "root",
      "name": "Máy tính xách tay",
      "children": []
    }
  ]
}
~~~

Mô hình này có các lợi ích:

- JSON có cấu trúc cây rõ ràng và không cần tham chiếu object ngược.
- Client biết quan hệ cha-con thông qua **parentId** và **children**.
- Schema có thể mô tả bằng một component tự tham chiếu.
- Có thể giới hạn độ sâu khi xây dựng DTO.
- Không phụ thuộc vào cách Jackson xử lý entity quan hệ hai chiều.

Nếu dữ liệu là đồ thị có nhiều quan hệ dùng chung hoặc có chu trình, nên cân nhắc mô hình **nodes + edges**:

~~~json
{
  "nodes": [
    { "id": "a", "name": "A" },
    { "id": "b", "name": "B" },
    { "id": "c", "name": "C" }
  ],
  "edges": [
    { "from": "a", "to": "b" },
    { "from": "b", "to": "c" },
    { "from": "c", "to": "a" }
  ]
}
~~~

Với nodes và edges, mỗi node chỉ được định nghĩa một lần. Các quan hệ được biểu diễn bằng ID nên không phải lặp object lồng nhau hoặc tạo JSON cycle. Cách này phù hợp hơn khi có nhiều đường nối, quan hệ nhiều-nhiều hoặc chu trình thực sự.

## 7. Xử lý entity hai chiều bằng Jackson

Nếu cần serialize trực tiếp object graph có quan hệ hai chiều, Jackson cung cấp một số cơ chế. Mỗi cơ chế có cách biểu diễn JSON khác nhau; hãy chọn theo hợp đồng API.

### @JsonManagedReference và @JsonBackReference

**@JsonManagedReference** đánh dấu phía cha hoặc phía được serialize theo hướng tiến. **@JsonBackReference** đánh dấu phía ngược và được bỏ qua khi serialize để tránh đi vòng trở lại.

~~~java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

class CategoryEntity {

    public String id;

    @JsonBackReference
    public CategoryEntity parent;

    @JsonManagedReference
    public List<CategoryEntity> children;
}
~~~

Với cách này, JSON có thể đi từ node cha xuống children nhưng không serialize parent ngược từ mỗi child. Khi deserialize, Jackson có thể khôi phục liên kết back reference tương ứng.

Các annotation này hữu ích cho một cặp quan hệ cha-con. Nếu có nhiều quan hệ hai chiều trong cùng lớp, cần đặt tên reference phù hợp và bảo đảm mỗi cặp managed/back có định danh riêng. Không dùng chúng như một giải pháp tổng quát cho mọi đồ thị.

### @JsonIgnore

Nếu API không cần trường tham chiếu ngược, có thể loại trường đó khỏi JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

class CategoryEntity {

    public String id;
    public List<CategoryEntity> children;

    @JsonIgnore
    public CategoryEntity parent;
}
~~~

Đây là cách đơn giản nhưng parent sẽ không xuất hiện trong JSON. Nếu client cần quan hệ cha, hãy dùng **parentId** trong DTO thay vì bỏ qua hoàn toàn.

### @JsonIdentityInfo

**@JsonIdentityInfo** cho phép Jackson nhận diện object bằng ID. Lần đầu object xuất hiện, serializer ghi đầy đủ thuộc tính; những lần tham chiếu tiếp theo có thể chỉ ghi object ID.

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
class CategoryEntity {
    public String id;
    public CategoryEntity parent;
    public List<CategoryEntity> children;
}
~~~

JSON khi đó có thể chứa một object đầy đủ ở lần đầu và giá trị ID ở các vị trí tham chiếu sau. Hình dạng JSON không còn luôn là một object cùng schema tại mọi vị trí; một thuộc tính có thể là object hoặc ID scalar tùy nơi object đã xuất hiện.

Điều này có thể khó mô tả bằng một schema OpenAPI đơn giản. Nếu hợp đồng công khai cần cơ chế identity, hãy định nghĩa rõ kiểu tham chiếu và dùng schema phù hợp như **oneOf** nếu thực sự cho phép object hoặc ID. Đừng giả định springdoc luôn suy ra chính xác mọi biến thể JSON do identity serialization tạo ra.

## 8. Giới hạn độ sâu và kích thước cây

Schema đệ quy cho phép cấu trúc có nhiều cấp, nhưng API thực tế vẫn cần giới hạn để tránh response quá lớn, truy vấn dữ liệu quá sâu hoặc tiêu thụ bộ nhớ quá mức.

Các biện pháp thường dùng:

- Chỉ lấy tối đa một số cấp bằng tham số **maxDepth** hoặc **depth**.
- Phân trang danh sách con thay vì trả toàn bộ cây lớn trong một response.
- Dùng endpoint lấy children theo **parentId** khi cây rất lớn.
- Giới hạn số node tối đa trong một request.
- Kiểm tra quyền truy cập ở từng nhánh để không lộ dữ liệu con ngoài phạm vi.
- Dùng truy vấn projection để lấy đúng field cần thiết, tránh tải cả entity graph.

Ví dụ endpoint cho phép giới hạn độ sâu:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/categories/tree")
CategoryNodeView getTree(
    @RequestParam(defaultValue = "3") @Min(1) @Max(8) int maxDepth
) {
    return categoryService.loadTree(maxDepth);
}
~~~

OpenAPI cần mô tả parameter **maxDepth**, giá trị mặc định và giới hạn:

~~~yaml
parameters:
  - name: maxDepth
    in: query
    required: false
    description: Số cấp tối đa tính từ nút gốc
    schema:
      type: integer
      minimum: 1
      maximum: 8
      default: 3
~~~

Giới hạn trong schema giúp client hiểu hợp đồng, nhưng server vẫn phải kiểm tra và thực thi giới hạn ở runtime.

## 9. Mô tả schema đệ quy với annotation

Springdoc có thể suy luận quan hệ tự tham chiếu từ kiểu Java. Khi cần làm rõ tên component, mô tả hoặc kiểu của collection, có thể dùng **@Schema** và **@ArraySchema**.

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "CategoryNodeView",
    description = "Nút danh mục có thể chứa các nút con cùng kiểu"
)
public record CategoryNodeView(
    @Schema(description = "Mã nút", example = "root")
    String id,

    @Schema(description = "Tên nút", example = "Thiết bị")
    String name,

    @ArraySchema(
        arraySchema = @Schema(description = "Danh sách danh mục con"),
        schema = @Schema(implementation = CategoryNodeView.class)
    )
    List<CategoryNodeView> children
) {}
~~~

Với kiểu trả về là danh sách các nút gốc:

~~~java
@GetMapping("/api/categories/roots")
List<CategoryNodeView> getRoots() {
    return categoryService.loadRoots();
}
~~~

Schema response là array, trong đó **items** tham chiếu **CategoryNodeView**. Bản thân component **CategoryNodeView** lại chứa một array children tham chiếu cùng component.

Không cần đặt **@Schema(implementation = CategoryNodeView.class)** trên mọi thuộc tính tự tham chiếu nếu kiểu Java đã đủ rõ. Chỉ bổ sung annotation khi cần điều khiển tên, mô tả, ví dụ hoặc kiểu schema. Sau đó kiểm tra tài liệu sinh ra để tránh vô tình tạo component trùng tên hoặc làm mất tham chiếu.

## 10. Vòng tham chiếu giữa các schema và công cụ OpenAPI

Schema có thể tự tham chiếu hoặc tạo chu trình qua nhiều component. Công cụ hiển thị tài liệu, sinh client hoặc chuyển đổi OpenAPI có thể xử lý các trường hợp này khác nhau.

Khi gặp lỗi hoặc hiển thị không đúng:

1. Xác nhận JSON OpenAPI có component được định nghĩa.
2. Kiểm tra đường dẫn trong mọi **$ref** có tồn tại.
3. Kiểm tra component tự tham chiếu trỏ đến đúng tên và đúng cấp.
4. Kiểm tra schema array có **items** là component mong muốn.
5. Xem công cụ client generator có hỗ trợ recursive model hay không.
6. Nếu một công cụ cụ thể không hỗ trợ vòng tham chiếu, cân nhắc DTO phẳng hoặc mô hình ID/edges dành cho công cụ đó.

Ví dụ kiểm tra schema:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
jq '.components.schemas.CategoryNodeView' openapi.json
~~~

Kết quả mong đợi là property **children** có **type: array** và **items.$ref** trỏ về **#/components/schemas/CategoryNodeView**. Nếu springdoc tạo schema inline hoặc dùng tên component khác, hãy đọc đúng cấu trúc thực tế thay vì giả định tên cố định.

## 11. Kiểm thử serialization và tài liệu

Cần kiểm tra cả JSON runtime và OpenAPI. Hai kiểm tra này phát hiện hai loại lỗi khác nhau.

### Kiểm tra JSON không bị vòng lặp

Ví dụ kiểm thử DTO cây:

~~~java
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CategorySerializationTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void serializesFiniteTree() throws Exception {
        CategoryNode node = new CategoryNode(
            "root",
            "Thiết bị",
            List.of(
                new CategoryNode("laptop", "Máy tính xách tay", List.of())
            )
        );

        String json = objectMapper.writeValueAsString(node);

        assertThat(json).contains("\"id\":\"root\"");
        assertThat(json).contains("\"id\":\"laptop\"");
        assertThat(json).contains("\"children\":[]");
    }
}
~~~

Kiểm thử này xác nhận DTO cây có thể được serialize thành JSON hữu hạn. Nếu DTO dùng annotation Jackson hoặc custom serializer, hãy dùng ObjectMapper được cấu hình giống ứng dụng.

### Kiểm tra OpenAPI có self-reference

Có thể viết kiểm thử tích hợp lấy **/v3/api-docs**, đọc bằng Jackson rồi kiểm tra component:

~~~java
JsonNode openApi = objectMapper.readTree(
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString()
);

JsonNode childrenItems = openApi
    .path("components")
    .path("schemas")
    .path("CategoryNodeView")
    .path("properties")
    .path("children")
    .path("items");

assertThat(childrenItems.path("$ref").asText())
    .isEqualTo("#/components/schemas/CategoryNodeView");
~~~

Đoạn kiểm thử giả định test class đã có **MockMvc**, **ObjectMapper** và static imports cho MockMvc/AssertJ. Nếu schema được đặt tên khác hoặc inline, điều chỉnh đường dẫn assertion theo tài liệu thực tế.

## 12. Lỗi thường gặp

**Swagger UI hiển thị schema lồng nhau nhưng response bị lỗi lồng quá sâu.** Kiểm tra object graph runtime có tham chiếu ngược hay không. Schema tự tham chiếu là hợp lệ, nhưng object cha-con hai chiều có thể tạo vòng lặp khi Jackson serialize. Chuyển sang DTO một chiều, dùng parentId hoặc cấu hình Jackson identity phù hợp.

**Schema chỉ hiển thị một cấp children.** Kiểm tra kiểu phần tử collection có đúng kiểu đệ quy hay không và **items** có tham chiếu component tương ứng không. Nếu dùng DTO khác nhau ở mỗi cấp, schema sẽ không tự đệ quy.

**OpenAPI có $ref trỏ đến component không tồn tại.** Kiểm tra tên component, annotation **@Schema(name = ...)** và customizer đã thay đổi schema. Mọi local reference cần trỏ đến một phần tử có thật trong **components.schemas**.

**JSON lặp object hoặc response quá lớn.** Kiểm tra entity graph, lazy relation và cách mapper chuyển entity thành DTO. Đặt giới hạn độ sâu, phân trang hoặc tải children theo yêu cầu.

**Client generator không xử lý recursive model.** Xác định giới hạn của generator đang dùng. Có thể công bố một DTO phẳng hoặc mô hình nodes/edges để client dễ xử lý hơn, trong khi vẫn giữ mô hình nội bộ của server.

**@JsonIdentityInfo tạo lúc là object, lúc là ID.** Schema cần mô tả chính xác biến thể này. Nếu client khó xử lý, cân nhắc thiết kế response DTO có trường ID riêng và không dùng object identity serialization cho hợp đồng công khai.

## 13. Checklist thiết kế API đệ quy

- [ ] Xác định dữ liệu là cây, nhiều cây hay đồ thị có chu trình.
- [ ] Dùng DTO tự tham chiếu để mô tả cây có độ sâu thay đổi.
- [ ] Đảm bảo mọi local **$ref** trỏ đến component hợp lệ.
- [ ] Phân biệt vòng tham chiếu schema với vòng tham chiếu object Java.
- [ ] Tránh trả trực tiếp entity JPA có quan hệ hai chiều nếu chưa kiểm soát serialization.
- [ ] Chọn DTO một chiều, parentId hoặc nodes/edges cho quan hệ phức tạp.
- [ ] Nếu dùng Jackson identity annotations, xác minh hình dạng JSON và schema tương ứng.
- [ ] Giới hạn độ sâu, số node và chi phí truy vấn.
- [ ] Kiểm tra serialization thực tế và OpenAPI JSON.
- [ ] Kiểm tra Swagger UI và khả năng xử lý recursive model của client generator.

## 14. Kết luận

Schema đệ quy cho phép OpenAPI mô tả dữ liệu phân cấp với độ sâu không cố định thông qua **$ref**. springdoc có thể suy luận kiểu tự tham chiếu từ DTO Java và tạo component tương ứng. Tuy nhiên, vòng tham chiếu trong schema khác với vòng lặp của object graph khi Jackson serialize. Hãy chọn mô hình cây hoặc đồ thị đúng với nghiệp vụ, dùng DTO có cấu trúc JSON hữu hạn, kiểm soát độ sâu và xác minh cả response runtime lẫn schema được sinh ra.

## 15. Nguồn tham khảo

- [OpenAPI Specification — Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): cấu trúc Schema Object và tham chiếu schema trong OpenAPI.
- [Jackson Annotations — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html): đánh dấu phía tham chiếu tiến trong quan hệ hai chiều.
- [Jackson Annotations — JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html): đánh dấu phía tham chiếu ngược khi serialize và deserialize.
- [Jackson Annotations — JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html): biểu diễn identity của object bằng ID.
- [Springdoc OpenAPI documentation](https://springdoc.org/): tạo và tùy biến schema OpenAPI từ ứng dụng Spring Boot.
