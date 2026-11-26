# Cân nhắc GraphQL khi cần API trên đồ thị và kiểm soát chi phí truy vấn

Neo4j rất phù hợp để mô hình hóa dữ liệu có nhiều liên kết. Một trang quản lý dự án có thể cần thông tin dự án, danh sách công việc, thành viên và trạng thái hoàn thành; ứng dụng gợi ý có thể cần đi qua nhiều bước quan hệ. **GraphQL** cho phép client khai báo cấu trúc dữ liệu muốn nhận trong một request. Tuy nhiên, việc client chọn được nhiều nhánh dữ liệu cũng có nghĩa server phải kiểm soát **số node, relationship, hàng trung gian và phép truy vấn thực sự được thực thi**.

Bài học nằm trong chương **Thiết kế ứng dụng** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module sử dụng Neo4j để tổ chức **property graph**, truy vấn node, relationship và đường đi bằng Cypher, thiết kế index/constraint, và tích hợp qua Java Driver hoặc Spring Data Neo4j. Trong bối cảnh đó, GraphQL là **một lựa chọn cho tầng API**, không phải ngôn ngữ thay thế Cypher hay một cơ chế tự động làm cho truy vấn đồ thị nhanh hơn.

Sau bài này, bạn có thể:

- Quyết định trường hợp nào GraphQL mang lại lợi ích so với REST hoặc API chuyên biệt.
- Thiết kế GraphQL schema phản ánh node, relationship và property của relationship mà không buộc lộ toàn bộ cấu trúc Neo4j.
- Nhận diện lỗi **N+1**, fan-out, truy vấn lồng sâu, alias lặp và các phép tổng hợp đắt tiền.
- Áp dụng giới hạn độ sâu, complexity budget, phân trang, số hàng tối đa, timeout và kiểm soát truy cập theo tenant.
- Liên hệ mỗi GraphQL operation với Cypher/`EXPLAIN`/`PROFILE` và các chỉ số vận hành.
- Triển khai một resolver đọc dữ liệu bằng Spring for GraphQL và `Neo4jClient`, rồi kiểm thử tính đúng đắn, quyền và hiệu năng.

## 1. GraphQL giải quyết vấn đề nào trong API trên đồ thị?

Giả sử màn hình chi tiết dự án cần:

~~~text
(:AppDemoUser {tenantId, userId})
       |
       | [:APP_MEMBER_OF {role, joinedAt}]
       v
(:AppDemoProject {tenantId, projectId, name})
       |
       | [:APP_HAS_TASK]
       v
(:AppDemoTask {tenantId, taskId, title, status, createdAt})
~~~

Trong mô hình này:

- **Node** `AppDemoUser`, `AppDemoProject` và `AppDemoTask` là các thực thể có định danh.
- **Relationship** `APP_MEMBER_OF` nối người dùng với dự án và có property `role`, `joinedAt`.
- **Relationship** `APP_HAS_TASK` nối dự án với công việc.
- `tenantId` xác định phạm vi tổ chức, không phải thuộc tính được client tùy ý chọn để vượt qua kiểm tra quyền.

Với REST, ứng dụng có thể cần gọi nhiều endpoint, chẳng hạn thông tin dự án rồi danh sách task và thành viên. Với GraphQL, client có thể yêu cầu các trường cần thiết trong một operation:

~~~graphql
query ProjectOverview($projectId: ID!, $taskLimit: Int!) {
  project(id: $projectId) {
    id
    name
    tasks(first: $taskLimit) {
      nodes {
        id
        title
        status
      }
      pageInfo {
        endCursor
        hasNextPage
      }
    }
  }
}
~~~

Operation trên chỉ có nghĩa nếu server đã định nghĩa schema và resolver phù hợp. GraphQL **không tự hiểu** label `AppDemoProject` hay relationship `APP_HAS_TASK` chỉ từ cú pháp query. Tầng API phải ánh xạ chúng thành dữ liệu và áp dụng quyền, lọc, phân trang.

### 1.1. Lợi ích và chi phí đi kèm

| Lợi ích thường gặp | Chi phí cần chấp nhận |
| --- | --- |
| Client chọn đúng field cần cho từng màn hình. | Server phải kiểm soát field nào được phép truy cập và chi phí của từng nhánh. |
| Một endpoint có thể trả nhiều thực thể liên kết. | Query lồng nhau có thể làm bùng nổ số lần truy vấn hoặc số bản ghi cần đọc. |
| Schema kiểu rõ ràng, hỗ trợ introspection và công cụ client. | Cần quản lý version/deprecation, nullability, lỗi và hợp đồng phân trang. |
| Có thể phát triển giao diện mà không tạo endpoint REST cho từng tổ hợp dữ liệu. | Phức tạp thêm về resolver, caching, tracing và kiểm soát độ phức tạp. |
| Thuận lợi khi nhiều client cần hình dạng dữ liệu khác nhau. | Một operation tùy biến khó dự đoán chi phí hơn endpoint cố định nếu không giới hạn. |

**GraphQL là lựa chọn API, không phải mục tiêu bắt buộc.** Nếu chỉ cần vài thao tác có kết quả cố định, REST cùng câu Cypher được tối ưu có thể đơn giản, an toàn và dễ cache hơn.

## 2. Khi nào nên cân nhắc GraphQL?

GraphQL có giá trị khi **các client có nhu cầu chọn trường và kết hợp quan hệ rất khác nhau**, ví dụ web, mobile và bảng điều khiển nội bộ dùng cùng miền dữ liệu. Nó cũng hữu ích khi schema giúp nhóm frontend khám phá và sử dụng hợp đồng API rõ ràng.

Ngược lại, một API báo cáo xuất một tệp lớn, luồng ingest tuần tự, tác vụ tính toán đường đi nặng hay endpoint tìm kiếm với thứ tự cố định có thể thích hợp hơn với REST, job bất đồng bộ hoặc API chuyên biệt.

| Yêu cầu | Hướng ưu tiên xem xét | Lý do |
| --- | --- | --- |
| Nhiều màn hình cần các tập field khác nhau trên cùng dữ liệu liên kết. | GraphQL với resolver có giới hạn. | Giảm việc tạo nhiều biến thể endpoint chỉ khác hình dạng kết quả. |
| Tra cứu node theo khóa, CRUD đơn giản, response cố định. | REST hoặc GraphQL đều được; chọn phương án ít phức tạp hơn. | GraphQL không đem lại lợi ích rõ nếu client không cần lựa chọn. |
| Tính top-K đường đi, thuật toán GDS hoặc xuất hàng triệu hàng. | API job bất đồng bộ/endpoint chuyên biệt. | Khó bảo đảm thời gian và tài nguyên cho operation đọc tương tác. |
| Public API có nhiều client không tin cậy. | GraphQL **chỉ khi** có giới hạn mạnh và quyền chi tiết. | Client có thể gửi truy vấn tốn kém dù hợp lệ về schema. |
| Tìm kiếm toàn văn/vector, phân trang và lọc nghiệp vụ phức tạp. | Resolver chuyên biệt sử dụng Cypher/index phù hợp. | Không nên để client tùy ý diễn đạt những traversal không giới hạn. |

Không nên quyết định chỉ theo tiêu chí “đồ thị thì phải dùng GraphQL”. Câu hỏi đúng là: **có cần một hợp đồng truy vấn linh hoạt cho client và có đủ khả năng kiểm soát chi phí của sự linh hoạt đó không?**

## 3. Từ property graph sang GraphQL schema

GraphQL có các object type, field, argument, list, input và scalar. Một schema thủ công có thể công bố **mô hình API** mà không lộ tất cả property trên Neo4j.

~~~graphql
type Query {
  project(id: ID!): Project
  projects(first: Int!, after: String): ProjectConnection!
}

type Project {
  id: ID!
  name: String!
  openTaskCount: Int!
  tasks(first: Int!, after: String): TaskConnection!
  members(first: Int!, after: String): MembershipConnection!
}

type Task {
  id: ID!
  title: String!
  status: String!
}

type Member {
  id: ID!
  displayName: String!
}

type Membership {
  member: Member!
  role: String!
  joinedAt: String
}

type PageInfo {
  endCursor: String
  hasNextPage: Boolean!
}

type ProjectConnection {
  nodes: [Project!]!
  pageInfo: PageInfo!
}

type TaskConnection {
  nodes: [Task!]!
  pageInfo: PageInfo!
}

type MembershipConnection {
  nodes: [Membership!]!
  pageInfo: PageInfo!
}
~~~

Đây là **GraphQL SDL thuần**, chưa khai báo logic resolver. Trong ứng dụng thực, có thể thêm các kiểu scalar ngày/giờ và enum trạng thái/vai trò theo thư viện đã lựa chọn. `joinedAt: String` chỉ là cách đơn giản hóa ví dụ; định dạng UTC, timezone và nullability vẫn cần hợp đồng rõ ràng.

### 3.1. Ánh xạ dữ liệu ở các lớp

| Property graph Neo4j | GraphQL API | Nguyên tắc |
| --- | --- | --- |
| `AppDemoProject.projectId` | `Project.id` | ID ở API có thể khác tên property vật lý. |
| `AppDemoProject.name` | `Project.name` | Trường có thể lấy trực tiếp từ node. |
| `(Project)-[:APP_HAS_TASK]->(Task)` | `Project.tasks` | Danh sách cần lọc quyền, phân trang và thứ tự. |
| `(User)-[r:APP_MEMBER_OF]->(Project)` | `Project.members.nodes[].member` | Trả người dùng liên quan. |
| `r.role` và `r.joinedAt` | `Membership.role`, `Membership.joinedAt` | Property của relationship được biểu diễn như một object trong API. |
| `tenantId` | Thường **không mở cho client ghi tùy ý** | Phạm vi tenant lấy từ ngữ cảnh xác thực và ủy quyền. |

`Membership` trong schema GraphQL là **kiểu kết quả API**. Nó không bắt buộc Neo4j có một node `:Membership`. Resolver có thể dựng object này từ relationship `APP_MEMBER_OF` và node `AppDemoUser`. Khi relationship là một thực thể có vòng đời độc lập, có thể cân nhắc mô hình khác; đó là quyết định modeling, không phải quy định của GraphQL.

### 3.2. Không buộc API phản chiếu 1:1 toàn bộ graph

Nếu Neo4j có đường đi `User → Group → Project → Task → Comment → Author`, không nhất thiết công bố tất cả thành field nối tiếp cho bất kỳ client nào. Có thể tạo:

- `ProjectSummary` cho màn hình danh sách.
- `Project.tasks(first, after)` để đi một cấp có giới hạn.
- `searchTasks(query, first)` là resolver chuyên biệt dùng full-text index.
- `relatedProjects(projectId, first)` là một phép xếp hạng/top-K được kiểm soát.

GraphQL cho phép mô hình hóa API **theo use case**, thay vì cho client đi qua mọi relationship mà Neo4j lưu.

## 4. Hai hướng triển khai phổ biến với Neo4j

### 4.1. Tự viết resolver

Một server GraphQL (chẳng hạn **Spring for GraphQL** trong ứng dụng Java) có thể gọi:

1. `Neo4jClient` hoặc Neo4j Java Driver để chạy Cypher có tham số.
2. Spring Data Neo4j repository đối với thao tác aggregate phù hợp.
3. Service nghiệp vụ để xác thực quyền, kiểm tra tham số và quản lý transaction.

Ưu điểm là kiểm soát chính xác Cypher, số hàng, cách phân trang và logic bảo mật. Nhược điểm là phải tự thiết kế các resolver, batching, mapping và observability.

### 4.2. Sinh các thao tác GraphQL từ model Neo4j

Hệ sinh thái Neo4j có các thư viện như **Neo4j GraphQL** (phổ biến trong JavaScript/TypeScript) hỗ trợ xây API từ type definition và relationship mapping. Các thư viện dạng này có thể giúp sinh các truy vấn, bộ lọc hoặc mutation cho mô hình đã khai báo. Tuy nhiên:

- **Cú pháp directive, tính năng authorization, pagination và phương thức truy vấn có thể khác theo phiên bản thư viện.**
- Resolver sinh tự động vẫn có thể tốn kém nếu schema cho phép đi qua relationship bậc lớn.
- Không được mặc định thư viện tự hiểu ranh giới tenant, quy tắc quyền hoặc chi phí kinh doanh của từng operation.
- Các tính năng generate CRUD không phải lý do để công khai mọi label/property của database.

Khi chọn thư viện tự sinh, hãy kiểm tra **Cypher thực tế được tạo**, tài nguyên tiêu thụ và những field/operation được xuất ra theo version đang triển khai. Khi một luồng nghiệp vụ yêu cầu logic ghi đặc biệt, có thể thay bằng resolver/service tường minh.

## 5. Vì sao GraphQL trên đồ thị có thể rất đắt?

Độ phức tạp GraphQL không chỉ phụ thuộc độ dài văn bản query. Cần xét **độ rộng của mỗi nhánh**, bậc node và các phép tổng hợp/sắp xếp phía Neo4j.

Giả sử một operation yêu cầu:

~~~graphql
query Dashboard {
  projects(first: 100) {
    nodes {
      id
      tasks(first: 50) {
        nodes {
          id
          comments(first: 10) {
            nodes {
              id
              text
            }
          }
        }
      }
    }
  }
}
~~~

Nếu dữ liệu đủ nhiều và các field đều trả đến giới hạn, operation có thể đi qua:

~~~text
100 project
  x 50 task / project = 5.000 task
  x 10 comment / task = 50.000 comment
~~~

Chỉ ba tầng danh sách đã tạo khả năng trả hàng chục nghìn object. Kể cả các giới hạn từng field đều “có vẻ nhỏ”, **tích của chúng** vẫn lớn. Nếu muốn tính thêm `members`, `attachments` và các trường tổng hợp, chi phí còn tăng.

Không nhầm **số object trả về** với **số relationship thực tế đã duyệt**. Một resolver có thể trả 10 kết quả sau khi đã duyệt hàng trăm nghìn relationship để chọn ra top 10.

### 5.1. N+1 query

Một cách triển khai resolver ngây thơ:

~~~text
1 query: lấy 100 project
100 query: lấy task của từng project
5.000 query: lấy comment của từng task
~~~

Đây là vấn đề **N+1** ở tầng resolver. Tổng số round-trip đến Neo4j tăng theo số parent object, kể cả khi mỗi câu Cypher riêng khá nhanh.

Các cách giảm N+1:

- **Batch loading:** gom nhiều projectId thành một lần đọc task, dùng DataLoader hoặc cơ chế tương đương.
- **Projection theo màn hình:** một câu Cypher có kiểm soát trả summary thay vì nhiều resolver lồng nhau.
- **Fetch có chọn lọc:** chỉ đọc field client yêu cầu, không tải toàn bộ aggregate SDN với các relationship không cần thiết.
- **Cache trong phạm vi request:** tránh đọc cùng node lặp lại ở các nhánh; cache liên request cần thêm chính sách invalidation và cách ly tenant.

Nhưng batching **chỉ giảm số round-trip**, không tự giảm tổng số node/relationship cần xử lý. Nếu batch query mở rộng hàng triệu cạnh, nó có thể vẫn rất chậm.

### 5.2. Fan-out và supernode

Giả sử một dự án có 200.000 task. Query GraphQL chỉ yêu cầu top 20 task mới nhất. Nếu Neo4j không thể dùng điểm bắt đầu hoặc cấu trúc dữ liệu phù hợp, hệ thống có thể cần duyệt rất nhiều cạnh rồi mới sắp xếp/giới hạn.

Tương tự, một task nổi tiếng có 1 triệu comment làm mọi phép mở rộng qua `HAS_COMMENT` trở nên đắt. Các đặc điểm này là **giới hạn do phân bố dữ liệu**, không thể sửa chỉ bằng cấu trúc SDL.

### 5.3. Sắp xếp và tổng hợp

Các field như `totalComments`, `memberCount`, `topContributors` có thể yêu cầu đếm/tổng hợp trên tập lớn. Ví dụ, `COUNT` qua nhiều nhánh kết hợp có thể tạo hàng trung gian khổng lồ nếu không phân tách phép tổng hợp.

Chi phí các field cần được tính theo **workload thực tế**: top-K có thể rẻ nếu có dữ liệu tính sẵn, nhưng đắt nếu phải quét mọi sự kiện rồi sort trước khi chọn K.

### 5.4. GraphQL alias, fragment và batch operation

Client có thể đặt bí danh:

~~~graphql
query RepeatedFields {
  a: projects(first: 50) { nodes { id name } }
  b: projects(first: 50) { nodes { id name } }
  c: projects(first: 50) { nodes { id name } }
}
~~~

Query không sâu nhưng yêu cầu ba nhánh gốc. Fragment giúp tái sử dụng các field trong tài liệu, **không giảm chi phí truy xuất dữ liệu**. Một số server cho phép nhiều operation hoặc batch HTTP request tùy cấu hình; gateway cần quản lý chi phí **toàn request và toàn người dùng**, không chỉ kiểm tra độ sâu một nhánh.

## 6. Thiết kế giới hạn độ phức tạp có thể thi hành

Không có một con số “độ sâu tối đa” phù hợp cho mọi GraphQL API. Cần kết hợp các lớp bảo vệ:

| Lớp bảo vệ | Cách làm | Giới hạn |
| --- | --- | --- |
| Giới hạn độ sâu (*depth limit*) | Từ chối operation lồng quá số tầng cho phép. | Không chặn được một tầng có quá nhiều phần tử hoặc alias. |
| Complexity budget | Gán trọng số cho từng field và nhân theo số phần tử tối đa. | Chỉ là ước lượng; không thay số liệu hiệu năng từ Neo4j. |
| Giới hạn `first`/`pageSize` | Yêu cầu giá trị dương, đặt max theo từng collection. | Nhiều tầng collection vẫn có thể nhân chi phí. |
| Giới hạn số alias và field | Chặn việc lặp field/tổ hợp quá lớn trong cùng request. | Cần xét fragment, operation và biến đầu vào. |
| Giới hạn thời gian | Timeout ở gateway, resolver/driver và transaction theo chính sách. | Hủy HTTP không bảo đảm query DB dừng ngay nếu không tích hợp đúng. |
| Giới hạn tài nguyên | Rate limit, concurrency, số request/tenant, giới hạn kết quả. | Cần thêm fairness và giám sát trường hợp dùng nhiều kết nối. |
| Operation allowlist | Client được chạy tập operation đã phê duyệt, đặc biệt cho ứng dụng nội bộ. | Vẫn phải xác thực quyền, validate biến và đo chi phí theo dữ liệu. |

### 6.1. Mô hình tính complexity minh họa

Giả sử trường scalar có trọng số 1; `projects` có overhead 5 mỗi lần gọi, `tasks` có overhead 3 và số phần tử tối đa bị chặn tại `first`; `comments` có overhead 4. Một dạng ước lượng đơn giản là:

\[
C(\text{field}) =
w_{\text{field}} +
\text{maxItems(field)}\times
\sum C(\text{child fields}).
\]

Với field scalar, có thể xem `maxItems = 1`. Với danh sách, `maxItems` là giới hạn **server chấp nhận**, không phải chỉ số client khai báo khi nó vượt max.

Ví dụ một phép ước lượng thủ công:

~~~text
projects(first: 20)
  tasks(first: 30)
    comments(first: 10)

Số phần tử comment tối đa theo cây:
20 x 30 x 10 = 6.000
~~~

Nếu API đặt budget tương đương tối đa 1.000 phần tử cho operation tương tác, cấu trúc trên cần bị từ chối hoặc yêu cầu client thu hẹp phạm vi. Con số 1.000 chỉ là **ví dụ thiết kế chính sách**, không phải giới hạn mặc định của Neo4j hay GraphQL.

**Đừng chỉ cộng điểm các field:** một field tên `shortestPath` hoặc `allConnections` có thể tốn rất nhiều công việc dù trả ít dòng. Nó cần trọng số, giới hạn độ dài đường đi, quy tắc thuật toán và quyền được sử dụng riêng.

### 6.2. Clamp input ngay tại ranh giới API

Giả sử `tasks(first: Int!)` cho phép tối đa 50:

- Từ chối giá trị 0 hoặc âm thay vì chạy query không có ý nghĩa.
- Từ chối giá trị quá 50 hoặc áp dụng chính sách clamp đã công bố, thống nhất giữa validator và resolver.
- Giới hạn độ dài bộ lọc văn bản, số phần tử trong `ids` và kích thước `where` lồng nhau.
- Không để người dùng quyết định độ dài đường đi Cypher không giới hạn kiểu `*1..` nếu API chỉ nên truy cập 2–3 hop.
- Bảo vệ cả query qua WebSocket/subscription nếu tính năng này được bật.

Chi phí cần tính **sau khi GraphQL áp dụng biến** vì `first: $pageSize` có thể là 5 hoặc 50. Chỉ đọc source text mà bỏ qua giá trị biến là không đủ.

## 7. Phân trang từ GraphQL đến Neo4j

Một danh sách có thể thay đổi theo thời gian, nên phân trang phải có **thứ tự ổn định**. Đừng trả kết quả phụ thuộc thứ tự duyệt relationship mặc định.

### 7.1. Offset: dễ hiểu nhưng có giới hạn

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
RETURN p.projectId AS id, p.name AS name
ORDER BY id ASC
SKIP $offset
LIMIT $pageSize;
~~~

`$offset` là số nguyên không âm và `$pageSize` phải được chặn tối đa. Khi offset lớn, Neo4j có thể vẫn phải xử lý/bỏ qua nhiều kết quả trước đó. Nếu tập dữ liệu thay đổi giữa hai request, việc thêm/xóa bản ghi có thể làm một số phần tử xuất hiện lại hoặc bị bỏ sót.

### 7.2. Keyset/cursor: phù hợp danh sách ổn định hơn

Nếu `projectId` là duy nhất **trong tenant** và sắp theo chiều tăng:

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
WHERE p.projectId > $afterProjectId
RETURN p.projectId AS id, p.name AS name
ORDER BY id ASC
LIMIT $pageSize;
~~~

Ở trang đầu, resolver có thể dùng query không có điều kiện `p.projectId > $afterProjectId`; các trang sau giải mã cursor và xác minh giá trị đầu vào. Cursor nên là **opaque token** gắn với thứ tự và bộ lọc; không dựa vào nội dung token do client sửa để quyết định quyền.

Nếu sắp theo `createdAt DESC`, cần thêm khóa phụ duy nhất như `projectId` để phá hòa và xây điều kiện keyset tương ứng. Khi giá trị sắp xếp bị sửa trong lúc phân trang, cursor vẫn không tự tạo snapshot nhất quán; hãy xác định semantics mà sản phẩm chấp nhận.

### 7.3. Lấy thêm một hàng để tính hasNextPage

Một cách phổ biến: client yêu cầu 20 bản ghi, resolver đọc tối đa **21** hàng theo thứ tự, trả 20 và đặt `hasNextPage = true` nếu hàng thứ 21 tồn tại. Không cần chạy `count(*)` trên toàn bộ dữ liệu chỉ để biết có trang tiếp hay không.

Với connection chứa dữ liệu lồng nhau, cần thiết kế phân trang **theo từng parent**. Một `LIMIT 20` đặt sau khi mở rộng task của 10 project không đồng nghĩa mỗi project được trả tối đa 20 task; nó có thể giới hạn tổng số hàng toàn truy vấn và khiến một project chiếm hết kết quả.

## 8. Batching đúng cách và tránh mất giới hạn theo parent

Giả sử resolver `Project.tasks(first: 10)` được gọi trên 30 project. Thay vì 30 request Cypher, có thể batch theo danh sách projectId được phép.

Ví dụ minh họa bằng một câu Cypher với giới hạn mỗi project:

~~~cypher
UNWIND $projectIds AS projectId
MATCH (p:AppDemoProject {
  tenantId: $tenantId,
  projectId: projectId
})
CALL {
  WITH p
  MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId
  RETURN t
  ORDER BY t.createdAt DESC, t.taskId ASC
  LIMIT $perParent
}
RETURN p.projectId AS projectId,
       collect({
         id: t.taskId,
         title: t.title,
         status: t.status
       }) AS tasks
ORDER BY projectId;
~~~

Ở đây, subquery tương quan được thực thi cho từng parent `p` và đặt `LIMIT $perParent` **bên trong**, không phải một `LIMIT` chung sau toàn bộ `UNWIND`. Cú pháp và hành vi của correlated subquery có khác biệt theo dòng Neo4j/Cypher; hãy kiểm tra trên phiên bản đang chạy.

**Các điểm phải xử lý ở resolver/DataLoader:**

1. Nếu một project không có task, subquery `MATCH` không trả hàng và project đó có thể vắng khỏi kết quả. DataLoader phải trả **danh sách rỗng** cho key hợp lệ không có task, thay vì làm lệch thứ tự kết quả.
2. `projectIds` phải bị giới hạn về số phần tử, loại trùng và được lọc quyền; không biến batching thành đọc không giới hạn.
3. Khi các parent yêu cầu `first`, cursor hoặc filter **khác nhau**, không gộp chung rồi bỏ qua sự khác biệt. Có thể batch theo nhóm tham số tương đương hoặc tạo chiến lược riêng.
4. Ánh xạ kết quả phải theo **khóa projectId**, không dựa vào thứ tự hàng Neo4j trả về, trừ khi đã dựng lại thứ tự đúng với các key DataLoader nhận.
5. Có thể cần giới hạn việc thực thi subquery và số hàng trên toàn request, dù mỗi parent đã có limit.

Batching tối ưu **số lần round-trip**; kiểm soát fan-out, sort và quyền trong từng query vẫn là bắt buộc.

## 9. Tối ưu Cypher phía sau resolver

GraphQL schema có thể chỉ khai báo `projects(first: 20) { nodes { id name openTaskCount } }`, nhưng chi phí nằm ở Cypher mà resolver dùng.

### 9.1. Lọc, giới hạn parent rồi mới mở rộng

Một query thiết kế theo màn hình danh sách:

~~~cypher
MATCH (p:AppDemoProject {tenantId: $tenantId})
WITH p
ORDER BY p.projectId ASC
LIMIT $first
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId AND t.status = 'OPEN'
  RETURN count(t) AS openTaskCount
}
RETURN p.projectId AS id,
       p.name AS name,
       openTaskCount
ORDER BY id ASC;
~~~

Câu này chọn tối đa `$first` project trước khi đếm task. Nó tránh đếm task cho **mọi project trong tenant** chỉ để trả vài project đầu tiên. Tuy vậy, nếu một project có hàng trăm nghìn task, phép `count(t)` vẫn có thể phải duyệt nhiều quan hệ; khi đó cân nhắc mô hình summary được cập nhật có kiểm soát.

`WHERE t.tenantId = $tenantId` vừa giúp kiểm tra phạm vi dữ liệu, vừa nhấn mạnh bất biến cross-tenant. Nhưng vì điều kiện này xuất hiện ở phần mở rộng, đừng coi nó thay thế kiểm tra ủy quyền hoặc chứng minh engine không phải duyệt cạnh sai tenant.

### 9.2. Xem kế hoạch thực thi

~~~cypher
EXPLAIN
MATCH (p:AppDemoProject {tenantId: $tenantId})
WITH p
ORDER BY p.projectId ASC
LIMIT $first
CALL {
  WITH p
  OPTIONAL MATCH (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
  WHERE t.tenantId = $tenantId AND t.status = 'OPEN'
  RETURN count(t) AS openTaskCount
}
RETURN p.projectId AS id, openTaskCount
ORDER BY id ASC;
~~~

Dùng `PROFILE` **trên query đọc** và dữ liệu thử đại diện để biết số hàng/DB Hits/tài nguyên ở từng bước. Cần so sánh:

- Neo4j bắt đầu từ bao nhiêu project? Dùng index/range seek hay quét label?
- Có giới hạn project trước khi mở rộng `APP_HAS_TASK` không?
- Có bao nhiêu task được duyệt và loại ở bộ lọc `status`/`tenantId`?
- `count`, `Sort` hoặc `Top` có chiếm phần lớn thời gian/bộ nhớ không?
- Các tenant lớn hoặc project bậc cao có p95/p99 tệ hơn median bao nhiêu?

`EXPLAIN` không chạy query, còn `PROFILE` **thực thi query**; không bật `PROFILE` với mutation production tùy tiện. Tên toán tử/các cột thống kê thay đổi theo phiên bản Neo4j và runtime.

### 9.3. Index và constraint hỗ trợ điểm bắt đầu

Trên môi trường học tập:

~~~cypher
CREATE CONSTRAINT app_demo_project_key IF NOT EXISTS
FOR (p:AppDemoProject)
REQUIRE (p.tenantId, p.projectId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT app_demo_task_key IF NOT EXISTS
FOR (t:AppDemoTask)
REQUIRE (t.tenantId, t.taskId) IS UNIQUE;
~~~

Constraint uniqueness theo cặp property giúp bảo vệ khóa dự án và task trong tenant, đồng thời có cấu trúc chỉ mục hỗ trợ một số mẫu tra cứu. Nó **không** buộc mỗi property phải tồn tại khi dùng uniqueness constraint thông thường; cần validate payload hoặc cân nhắc key/existence constraint theo edition/phiên bản.

Không thêm index ngẫu nhiên khi `PROFILE` đã tìm đúng parent bằng index nhưng chậm chủ yếu do mở rộng quan hệ. Khi nút thắt là supernode hay số task cần tổng hợp, cần cân nhắc dữ liệu tính sẵn, giới hạn thời gian hoặc thay đổi mô hình.

### 9.4. Materialized count và dữ liệu tổng hợp

Nếu màn hình cần `openTaskCount` cho hàng nghìn request mỗi phút, có thể cân nhắc lưu property `AppDemoProject.openTaskCount` và cập nhật khi task đổi trạng thái. Đổi lại:

- Phải bảo đảm cập nhật count và thay đổi task trong cùng transaction nếu cùng Neo4j.
- Phải xử lý concurrent update, retry, delete và backfill.
- Cần query đối soát summary với dữ liệu gốc và cơ chế sửa khi sai.

Một field GraphQL trông rẻ vì chỉ đọc property có thể đã chuyển chi phí sang đường ghi. Đánh giá **tổng chi phí hệ thống**, không chỉ độ trễ của một resolver.

## 10. Spring for GraphQL + Neo4jClient: ví dụ một resolver an toàn hơn

Trong Java, **Spring for GraphQL** cung cấp tầng GraphQL controller và data fetching, còn Spring Data Neo4j cung cấp `Neo4jClient` để chạy Cypher. Hai thành phần này phục vụ những trách nhiệm khác nhau.

Định nghĩa schema chuyên cho màn hình danh sách, cố ý **không trả object lồng nhau vô hạn**:

~~~graphql
type Query {
  projects(first: Int!): [ProjectSummary!]!
}

type ProjectSummary {
  id: ID!
  name: String!
  openTaskCount: Int!
}
~~~

Mẫu Java 17+:

~~~java
import java.security.Principal;
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

record ProjectSummary(String id, String name, int openTaskCount) {}

interface TenantScope {
    // Triển khai phải xác thực quyền tenant từ principal đã xác minh.
    String requireTenant(Principal principal);
}

@Controller
public class ProjectGraphQlController {
    private final Neo4jClient neo4jClient;
    private final TenantScope tenantScope;

    public ProjectGraphQlController(
            Neo4jClient neo4jClient, TenantScope tenantScope) {
        this.neo4jClient = neo4jClient;
        this.tenantScope = tenantScope;
    }

    @QueryMapping
    public List<ProjectSummary> projects(
            @Argument int first, Principal principal) {
        if (first < 1 || first > 50) {
            throw new IllegalArgumentException(
                "first phải trong khoảng 1..50");
        }

        // KHÔNG nhận tenantId do client tự khai báo làm phạm vi quyền.
        String tenantId = tenantScope.requireTenant(principal);

        return neo4jClient.query("""
                MATCH (p:AppDemoProject {tenantId: $tenantId})
                WITH p
                ORDER BY p.projectId ASC
                LIMIT $first
                CALL {
                  WITH p
                  OPTIONAL MATCH
                    (p)-[:APP_HAS_TASK]->(t:AppDemoTask)
                  WHERE t.tenantId = $tenantId
                    AND t.status = 'OPEN'
                  RETURN count(t) AS openTaskCount
                }
                RETURN p.projectId AS id,
                       p.name AS name,
                       openTaskCount
                ORDER BY id ASC
                """)
            .bind(tenantId).to("tenantId")
            .bind(first).to("first")
            .fetch()
            .all()
            .stream()
            .map(row -> new ProjectSummary(
                (String) row.get("id"),
                (String) row.get("name"),
                Math.toIntExact(
                    ((Number) row.get("openTaskCount")).longValue()
                )))
            .toList();
    }
}
~~~

**Giả định và giới hạn của ví dụ:**

1. `TenantScope` chỉ là hợp đồng minh họa. **Ứng dụng phải tự triển khai** từ principal và quyền đã được xác minh; không trả tenant mặc định nếu người dùng chưa xác thực.
2. Database chứa `AppDemoProject`, `AppDemoTask` và `APP_HAS_TASK` như mô hình trong bài. Nếu không có dữ liệu, query trả danh sách rỗng.
3. Server có cấu hình Spring for GraphQL, Neo4jClient, bảo mật và transaction/driver phù hợp. Đoạn mã không tự tạo một ứng dụng Spring Boot hoàn chỉnh.
4. GraphQL `Int` là số nguyên 32-bit. `Math.toIntExact(...)` cố ý phát hiện overflow khi count vượt miền đó; sản phẩm có thể dùng custom scalar/kiểu khác nếu số lượng thật vượt giới hạn.
5. Resolver clamp `first` nhưng **chưa thay thế** giới hạn complexity toàn operation, phân trang cursor hay timeout.
6. Query có một lượt đếm theo từng project được chọn; nếu mỗi project có rất nhiều task, phải đo và cân nhắc summary/materialization.
7. Phải kiểm thử rằng dữ liệu cross-tenant không thể được truy xuất thông qua các mối quan hệ sai phạm, kể cả khi node bắt đầu thuộc tenant hợp lệ.

Trong hệ thống thật, biến đầu vào có thể bị từ chối ở tầng GraphQL validation trước resolver. Không nên trả lỗi Neo4j thô hoặc stack trace ra client; chuẩn hóa lỗi có mã nghiệp vụ và giữ thông tin chẩn đoán nhạy cảm trong log server.

### 10.1. GraphQL query của client

~~~graphql
query Projects($first: Int!) {
  projects(first: $first) {
    id
    name
    openTaskCount
  }
}
~~~

Ví dụ variables:

~~~json
{"first": 20}
~~~

Điểm khác biệt so với ví dụ ở mục 1 là API danh sách này **chỉ trả summary**, không mở các field tùy ý để đi sâu vào từng task. Đây là lựa chọn chủ động khi yêu cầu hiệu năng/kiểm soát quyền quan trọng hơn tính linh hoạt.

## 11. Authorization: GraphQL field hợp lệ chưa chắc được phép đọc

GraphQL schema trả lời câu hỏi “field này tồn tại và có kiểu gì?”, **không tự trả lời** “người dùng hiện tại có quyền xem field này không?”.

### 11.1. Ba cấp độ kiểm soát

| Cấp | Ví dụ cần kiểm tra | Nơi thực thi |
| --- | --- | --- |
| Operation | User có quyền xem project hoặc gọi mutation quản trị không? | Gateway/controller/service. |
| Object/tenant | Project, task và member có thuộc phạm vi được phép không? | Trong query dữ liệu và/hoặc authorization service. |
| Field/relationship | User có quyền thấy `member.email` hay `membership.role` không? | Tại field resolver/projection; có thể yêu cầu lọc hoặc ẩn field. |

Một client có thể yêu cầu một project hợp lệ nhưng tiếp tục đi sang task/relationship của tenant khác nếu đồ thị chứa liên kết sai hoặc resolver không kiểm tra đủ. Mỗi bước mở rộng cần giữ **bất biến phạm vi dữ liệu**.

### 11.2. Không dựa vào tenantId từ input làm bằng chứng quyền

Không an toàn:

~~~graphql
query Unsafe($tenantId: ID!) {
  projectsForTenant(tenantId: $tenantId) {
    id
    name
  }
}
~~~

Operation trên **chỉ là ví dụ về một thiết kế có thể nguy hiểm nếu server tin thẳng tham số**. Vẫn có thể dùng `tenantId` làm tham số chọn tenant khi một user được cấp quyền nhiều tenant, nhưng server bắt buộc kiểm tra tenant đó thuộc tập được phép. Với người dùng chỉ có một tenant, nên lấy phạm vi từ identity/session thay vì tin client.

Tương tự, một GraphQL mutation không được cho phép client tự thay role, owner hoặc property phân quyền trên relationship chỉ vì schema có field đó.

### 11.3. Introspection và thông báo lỗi

Introspection giúp công cụ khám phá schema; có thể hạn chế hoặc điều chỉnh với public API tùy chính sách. Nhưng **tắt introspection không thay thế authorization**: kẻ tấn công vẫn có thể biết hoặc đoán field, và resolver vẫn phải kiểm tra quyền.

Không trả câu Cypher nội bộ, tên database, nội dung PII, secret hoặc chi tiết stack trace trong GraphQL error response. Log nội bộ nên chứa correlation ID để liên kết lỗi từ GraphQL xuống Neo4j, nhưng tránh log toàn bộ payload nhạy cảm.

## 12. Mutation và ranh giới giao dịch

GraphQL hỗ trợ loại operation `mutation`. Một mutation tạo dự án và các task liên quan cần được thực hiện theo **bất biến nghiệp vụ và transaction của Neo4j**, không chỉ dựa vào cú pháp GraphQL.

SDL minh họa:

~~~graphql
input CreateTaskInput {
  id: ID!
  title: String!
}

input CreateProjectInput {
  id: ID!
  name: String!
  tasks: [CreateTaskInput!]!
}

type Mutation {
  createProject(input: CreateProjectInput!): ProjectSummary!
}
~~~

Luồng service hợp lý:

~~~text
Xác thực và kiểm tra quyền
         |
Validate số task, ID, độ dài title
         |
BEGIN TRANSACTION Neo4j
         |
Tạo Project (khóa nghiệp vụ)
         |
Tạo Task + relationship APP_HAS_TASK
         |
Kiểm tra bất biến và COMMIT
         |
Trả kết quả đã ghi
~~~

Trong Java/Spring, có thể dùng `@Transactional` ở service đúng transaction manager Neo4j. Khi một bước thất bại, các thay đổi nằm trong transaction đó phải rollback. Nếu còn gửi email, thanh toán hoặc message broker, Neo4j transaction **không tự bao phủ các hệ thống bên ngoài**; cần outbox/idempotency hoặc cơ chế tích hợp thích hợp.

**Lưu ý GraphQL:** một HTTP request không tự đồng nghĩa với một transaction Neo4j bao trùm tất cả resolver. Một GraphQL mutation có thể có nhiều thao tác tùy cách server và thư viện triển khai; hãy định nghĩa ranh giới transaction ở service và không suy ra tính nguyên tử chỉ từ việc client gửi một operation.

Với mutation có thể bị retry do mất kết nối lúc commit, dùng **idempotency key** ổn định. Không tự kết luận rollback nếu client không nhận được response; kiểm tra trạng thái đã commit trước khi ghi lặp.

## 13. Kiểm soát quyền và chi phí với query động

Các filter GraphQL tự sinh có thể hỗ trợ các phép so sánh/phủ định, OR/AND lồng và lọc qua relationship. Chúng tiện lợi nhưng có thể làm một operation nhỏ về văn bản tương ứng với một câu Cypher phức tạp.

Ví dụ filter nhiều nhánh:

~~~graphql
query FilteredProjects($first: Int!) {
  projects(first: $first) {
    id
    name
    openTaskCount
  }
}
~~~

Ví dụ này cố ý chỉ có filter đơn giản về số lượng. Nếu API sau này bổ sung đầu vào như:

~~~graphql
input ProjectFilter {
  nameContains: String
  taskStatus: String
  memberRole: String
  or: [ProjectFilter!]
  and: [ProjectFilter!]
}
~~~

thì cần:

- Giới hạn **số điều kiện** và **độ sâu AND/OR**.
- Giới hạn kích thước danh sách và toán tử chuỗi/wildcard phức tạp.
- Áp dụng phép lọc tenant/permission từ server cùng lúc với filter do client yêu cầu.
- Xây whitelist của thuộc tính có thể lọc/sắp xếp và chỉ mục hỗ trợ; không cho client truyền cú pháp Cypher thô.
- Đo truy vấn **được sinh sau cùng**, không chỉ kiểm tra GraphQL AST.

Với GraphQL library có generator, hãy quan sát và test chính sách cho từng trường hợp filter/aggregate do thư viện hỗ trợ. Những tính năng, directive và cú pháp có thể thay đổi theo phiên bản; không giả định tên trường query tự sinh ở các release đều giống nhau.

## 14. Quan sát từ GraphQL đến Cypher và ngân sách vận hành

Khi API chậm, chỉ có metric “GraphQL response = 2 giây” là chưa đủ. Nên liên kết operation với query thực tế và workload:

| Metric | Ý nghĩa |
| --- | --- |
| GraphQL operation name và loại operation | Biết màn hình hoặc use case nào đang phát sinh tải. |
| Complexity/depth đã tính và số field thực thi | Phát hiện query quá rộng/sâu hoặc tăng số nhánh. |
| Số resolver và số lượt gọi Neo4j | Chỉ ra N+1 hoặc batching thiếu hiệu quả. |
| Thời gian Neo4j p50/p95/p99 | Phân biệt chậm ở DB với chậm trong resolver/network. |
| Rows/DB Hits, số relationship mở rộng ở query mẫu | Chỉ ra fan-out, Sort/Aggregation và index không phù hợp. |
| Bytes trả về và số object theo level | Theo dõi over-fetch và chi phí serialization. |
| Rate-limit reject, timeout, query bị hủy | Theo dõi hiệu quả bảo vệ tài nguyên và lỗi trải nghiệm. |
| Tenant/role dạng metadata đã kiểm soát | Chẩn đoán tải theo phạm vi, tránh lộ dữ liệu giữa tenant. |

Đặt **correlation ID** để nối một HTTP GraphQL request với log của resolver và Neo4j query. Không log nguyên query variables chứa password, token, email, tài liệu riêng tư hoặc nhiều dữ liệu người dùng không cần thiết. Có thể lưu operation hash/allowlisted name và một số tham số đã ẩn danh khi quan sát.

### 14.1. Phân biệt timeout ở từng tầng

- **Gateway/HTTP timeout**: tránh giữ kết nối client quá lâu.
- **Resolver/Java Driver timeout**: kiểm soát thời gian truy vấn hoặc transaction theo API đang sử dụng.
- **Giới hạn database và tài nguyên**: bảo vệ Neo4j trước quá nhiều request đồng thời, transaction kéo dài hoặc memory áp lực lớn.

Một HTTP timeout chỉ nói client không còn nhận kết quả; **không tự bảo đảm database đã dừng thao tác** nếu cơ chế cancel không được truyền xuống đúng cách. Đo cả transaction đang chạy và tỷ lệ hoàn tất/hủy ở Neo4j.

### 14.2. Khi nào sử dụng cache?

| Cấp cache | Hữu ích khi | Rủi ro |
| --- | --- | --- |
| Per-request DataLoader cache | Cùng node được nhiều field cần trong một operation. | Chỉ hữu ích trong một request, phải bảo đảm quyền. |
| Response cache theo operation + variables | Query đọc lặp, dữ liệu ít đổi. | Phải đưa identity/tenant/permission vào cache key hoặc chứng minh response công khai. |
| Cache theo entity/field | Nhiều màn hình đọc các thuộc tính gần như tĩnh. | Vô hiệu hóa khi entity/relationship đổi; dễ dùng dữ liệu cũ. |
| Materialized projection trong Neo4j | Aggregate/top-K đắt nhưng cập nhật chấp nhận được. | Tăng chi phí ghi và cần đối soát tính đúng đắn. |

Không chia sẻ cache response có dữ liệu riêng tư giữa người dùng hoặc tenant chỉ vì họ gọi cùng một operation GraphQL.

## 15. Kế hoạch kiểm thử API GraphQL trên Neo4j

Một test suite hiệu quả phải kiểm cả **đúng dữ liệu, đúng quyền và chặn được truy vấn quá đắt**. Không nên chỉ unit test một resolver với ba node.

| Test | Input / tình huống | Kỳ vọng |
| --- | --- | --- |
| G01 | Query một project hợp lệ. | Trả node và field đúng, không lộ property không công bố. |
| G02 | Project không tồn tại hoặc không thuộc quyền. | Trả kết quả/ lỗi theo chính sách, không tiết lộ dữ liệu tenant khác. |
| G03 | Một project có 0 task, một project có hàng nghìn task. | Pagination và `hasNextPage` đúng, không trả vượt giới hạn. |
| G04 | Query ba tầng danh sách với `first` lớn. | Complexity validator từ chối hoặc áp dụng ngân sách đã công bố. |
| G05 | Nhiều alias gọi cùng field nặng. | Chi phí tổng operation được tính, không vượt budget. |
| G06 | 100 project cần lấy task. | DataLoader/batching giảm round-trip; không làm sai thứ tự/quan hệ. |
| G07 | Hai parent dùng cursor/filter khác nhau. | Không dùng chung kết quả sai tham số, mỗi parent có trang đúng. |
| G08 | Query có filter AND/OR lồng sâu. | Validation từ chối vượt giới hạn; không chạy Cypher quá đắt. |
| G09 | Task nối sai tenant trong dữ liệu fixture. | Không trả task sai tenant, báo cảnh báo dữ liệu khi cần. |
| G10 | Mutation sai dữ liệu giữa chừng. | Transaction rollback, node và relationship không còn phần ghi dở. |
| G11 | Hai mutation cùng ID nghiệp vụ. | Constraint/idempotency ngăn dữ liệu trùng; lỗi được phân loại. |
| G12 | Client mất kết nối ngay lúc commit. | Có cách hòa giải trạng thái; không mặc định rollback rồi tạo lặp. |
| G13 | Project có bậc quan hệ rất lớn. | p95/p99 và tài nguyên trong giới hạn, hoặc request bị chặn đúng. |
| G14 | Một account thiếu quyền đọc field nhạy cảm. | Field bị ẩn/không cho truy cập đúng chính sách ở mọi đường query. |
| G15 | Server trả lỗi Cypher. | GraphQL error được chuẩn hóa, không lộ query nội bộ hoặc PII. |

### 15.1. Đo trên dữ liệu đại diện

Tối thiểu xây các nhóm dữ liệu:

1. Tenant nhỏ với vài project và vài task.
2. Tenant lớn có nhiều project, nhiều task và nhiều member.
3. Project rất đông (*supernode*), với task/comment vượt xa mức trung vị.
4. Dữ liệu đang cập nhật khi client phân trang.
5. Relationship trùng hoặc sai tenant để chứng minh resolver kiểm tra bất biến.

Ghi lại **baseline** trước và sau khi áp dụng batching, index hoặc giới hạn mới: số query Neo4j, Rows/DB Hits, p95, p99, bytes response, CPU/memory và kết quả nghiệp vụ. Một cải thiện N+1 có thể giảm từ 101 query xuống 2 query, nhưng nếu query mới xử lý số quan hệ quá lớn, độ trễ vẫn không cải thiện tương ứng.

### 15.2. Load test các operation thật

Không chỉ benchmark query `projects(first: 1) { nodes { id } }`; hãy lấy mẫu operation từ client thật theo trọng số:

- Danh sách dự án thường dùng.
- Chi tiết dự án với task và member.
- Tìm kiếm/phân trang theo filter.
- Operation admin được phép chạy nhưng có chi phí cao.
- Mutation cập nhật task và quan hệ.

So sánh cả thông lượng tối đa, lỗi timeout, tác động tới truy vấn khác dùng chung database và khả năng phục hồi sau đợt tải cao.

## 16. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| “GraphQL trả đúng trường nên tự động nhanh.” | Neo4j có thể đã mở rộng, sort và aggregate dữ liệu rất lớn rồi mới trả vài field. | Đo Cypher thực thi, Rows/DB Hits và độ trễ. |
| Chỉ giới hạn depth. | Query nông nhưng `first` lớn hoặc có nhiều alias vẫn đắt. | Kết hợp complexity, breadth, pagination và rate limit. |
| Chỉ đặt `LIMIT` cuối query Cypher. | Giới hạn có thể áp dụng sau khi đã mở rộng/tổng hợp lớn. | Chọn parent trước, giới hạn từng collection và đo kế hoạch. |
| Mỗi field resolver tự gọi DB. | Sinh N+1/1+N+M round-trip. | Dùng DataLoader, batch query và projection. |
| Batch rồi dùng một `LIMIT` cho tất cả parent. | Một parent chiếm cả trang, các parent khác thiếu dữ liệu. | Giới hạn theo parent bằng subquery/cách tương đương. |
| Expose mọi quan hệ Neo4j dưới dạng field. | Client có thể đi sâu, gây quá tải hoặc lộ cấu trúc/quan hệ nhạy cảm. | Thiết kế schema theo use case, chặn các traversal không cần. |
| Tin `tenantId` do client gửi. | Có nguy cơ đọc/ghi sang tenant khác. | Kiểm tra quyền tenant từ identity và từng bước mở rộng. |
| Dùng generated CRUD mà không xem quyền. | Các operation tự sinh có thể cho sửa field/relationship ngoài chính sách. | Cấu hình quyền, giới hạn và kiểm thử từng thao tác được expose. |
| Chỉ cache theo query text. | Cùng query có thể mang dữ liệu khác theo identity/tenant/variables. | Cache key gắn ngữ cảnh bảo mật và chính sách vô hiệu hóa. |
| GraphQL mutation được coi là một transaction phân tán. | External API/broker không tự rollback với Neo4j. | Thiết kế service transaction và idempotency/outbox. |
| Tắt introspection rồi coi là bảo mật. | Resolver vẫn thực thi nếu người dùng biết operation/field. | Authn/authz theo operation, object và field. |
| Áp dụng GraphQL cho báo cáo graph nặng tức thời. | Thuật toán nhiều phút làm cạn tài nguyên request. | Dùng job bất đồng bộ, báo trạng thái và trả kết quả giới hạn. |

## 17. Bài tập thực hành

**Bài 1 — Chọn kiến trúc API.** Một ứng dụng chỉ có hai endpoint tra cứu project theo ID và tạo task, với response cố định. Ứng dụng khác có web, mobile và admin cùng cần các tập trường liên kết khác nhau. Hãy so sánh REST và GraphQL về độ linh hoạt, bảo mật, caching, quan sát chi phí và công phát triển; đưa ra lựa chọn cho từng tình huống.

**Bài 2 — Thiết kế schema.** Từ graph `User-[APP_MEMBER_OF {role, joinedAt}]->Project-[APP_HAS_TASK]->Task`, viết SDL cho `Project`, `TaskConnection` và `MembershipConnection`. Giải thích vì sao `Membership` trong GraphQL không buộc phải là node Neo4j.

**Bài 3 — Ước lượng fan-out.** Một query lấy 40 project × 20 task/project × 12 comment/task. Tính số object comment tối đa. Nếu server chỉ cho phép ngân sách 3.000 comment/request, hãy đề xuất cách sửa operation hoặc đặt giới hạn.

**Bài 4 — Sửa N+1.** Resolver hiện gọi một query cho 100 project, rồi một query task cho từng project. Mô tả cách dùng DataLoader và query batch. Vì sao đặt `LIMIT 10` ở cuối câu batch không có nghĩa “mỗi project 10 task”?

**Bài 5 — Quyền multi-tenant.** Project A thuộc tenant T1, nhưng một task do lỗi dữ liệu có `tenantId = T2` và vẫn nối bằng `APP_HAS_TASK`. Xác định các điều kiện server phải kiểm tra khi resolver mở rộng từ project sang task, và các integration test để bảo đảm không lộ dữ liệu T2.

**Bài 6 — Khi nào dùng summary?** GraphQL field `openTaskCount` chậm vì một project có 300.000 task. So sánh việc đếm trực tiếp với lưu property tổng hợp trên Project. Đề xuất cách cập nhật, xử lý retry và đối soát nếu lưu summary.

**Bài 7 — Complexity budget.** Tự đặt trọng số cho `projects`, `tasks`, `comments` và scalar; viết công thức ước lượng khi `first` là biến, có alias và fragment. Chỉ rõ trường nào không thể đánh giá đúng nếu chỉ dựa vào depth.

**Bài 8 — Phân trang.** Viết query Cypher lấy trang tiếp theo của Project trong một tenant theo `projectId ASC`, sử dụng `afterProjectId`. Phân tích điều gì xảy ra nếu thêm/xóa project giữa hai trang và vì sao cursor không tự tạo snapshot dữ liệu.

**Bài 9 — Từ GraphQL đến PROFILE.** Một operation `project.tasks.comments` chậm 4 giây. Hãy liệt kê các bước chẩn đoán ở gateway, resolver, driver và Neo4j. Giải thích cách phân biệt lỗi N+1 với fan-out của một query đã batch.

**Bài 10 — Mutation và lỗi commit.** Mutation tạo một project cùng ba task; Neo4j commit nhưng client mất kết nối trước response. Thiết kế cách dùng idempotency key và tra cứu trạng thái đã lưu để tránh tạo trùng khi client retry.

## 18. Checklist khi đưa GraphQL API trên Neo4j vào production

1. **Nhu cầu thật:** nhiều client có cần chọn hình dạng dữ liệu linh hoạt hay REST/query chuyên biệt là đủ?
2. **Schema có chủ đích:** chỉ công bố field và đường đi phục vụ use case; relationship properties được ánh xạ thành kiểu API phù hợp.
3. **Quyền trước dữ liệu:** xác thực identity, kiểm tenant/object/field và không tin tham số client làm bằng chứng ủy quyền.
4. **Chi phí có giới hạn:** depth, breadth/alias, complexity, page size, filter, số query/timeout và concurrency đều có chính sách rõ.
5. **Resolver có thiết kế:** tránh N+1, batch theo đúng key và tham số, giới hạn kết quả **theo parent** khi cần.
6. **Cypher được đo:** có index/constraint phù hợp, `EXPLAIN`/`PROFILE` trên dữ liệu đại diện, chú ý fan-out và aggregate.
7. **Pagination ổn định:** có thứ tự xác định, cursor được kiểm soát và semantics khi dữ liệu thay đổi được giải thích.
8. **Mutation an toàn:** transaction rõ, validate đầu vào, khóa nghiệp vụ và idempotency khi retry.
9. **Quan sát liên tầng:** operation name/hash, resolver count, DB round-trip, Rows/DB Hits, latency p95/p99, bytes response và lỗi bảo vệ tài nguyên.
10. **Kiểm thử đa chiều:** đúng dữ liệu, multi-tenant, lỗi node/relationship, query lồng sâu, alias, tải lớn và tình huống mất kết nối.
11. **Version rõ ràng:** server GraphQL, Spring Data Neo4j/Java Driver hoặc thư viện Neo4j GraphQL có khả năng và syntax được kiểm chứng theo phiên bản triển khai.

**Kết luận:** GraphQL giúp client yêu cầu dữ liệu liên kết theo hình dạng phù hợp, nhưng **khả năng mô tả một truy vấn không đồng nghĩa nó rẻ hoặc được phép chạy**. Trên Neo4j, cần thiết kế schema theo use case, giới hạn phép duyệt đồ thị và số hàng, dùng resolver/batching phù hợp, kiểm soát quyền ở từng bước, rồi đo Cypher thực sự chạy. Chỉ nên chọn GraphQL khi lợi ích linh hoạt của API lớn hơn chi phí quản lý độ phức tạp, bảo mật và vận hành.
