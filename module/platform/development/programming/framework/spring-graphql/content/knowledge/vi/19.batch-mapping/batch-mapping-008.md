# Batch mapping trên interface

Trong GraphQL, interface mô tả một hợp đồng field chung cho nhiều object type. Ví dụ, một hệ thống hoạt động có thể trả về FooActivity và BarActivity. Cả hai đều có mã định danh và người điều phối, nhưng mỗi loại có dữ liệu riêng. Khi client truy vấn danh sách Activity và chọn field coordinator, GraphQL cần phân giải field này cho từng object thực tế.

Nếu resolver coordinator truy vấn người dùng riêng cho từng activity, một query lấy nhiều activity có thể tạo ra nhiều lần truy cập dữ liệu. **Batch mapping trên interface** cho phép gom các source object thuộc nhiều implementation của cùng interface vào một lần xử lý theo lô. Spring for GraphQL hỗ trợ cách này bằng annotation **@BatchMapping**: một batch handler được khai báo trên interface field có thể được áp dụng cho từng object type triển khai interface.

## Interface field và các object type triển khai

Giả sử schema có interface Activity và hai implementation:

~~~graphql
type Query {
  activities: [Activity!]!
}

interface Activity {
  id: ID!
  coordinator: User
}

type FooActivity implements Activity {
  id: ID!
  coordinator: User
  fooCode: String!
}

type BarActivity implements Activity {
  id: ID!
  coordinator: User
  barCategory: String!
}

type User {
  id: ID!
  name: String!
}
~~~

Field coordinator thuộc hợp đồng chung Activity. Vì FooActivity và BarActivity đều triển khai Activity, cả hai phải cung cấp field coordinator với kiểu output tương thích. Mỗi object vẫn có thể có field riêng như fooCode hoặc barCategory.

Client có thể truy vấn các field chung và dùng inline fragment cho dữ liệu riêng:

~~~graphql
query {
  activities {
    id
    coordinator {
      id
      name
    }
    __typename
    ... on FooActivity {
      fooCode
    }
    ... on BarActivity {
      barCategory
    }
  }
}
~~~

Field coordinator được yêu cầu cho mọi phần tử, bất kể phần tử là FooActivity hay BarActivity. Đây là trường hợp phù hợp để viết một batch mapping dùng chung cho interface.

## Vì sao batch mapping trên interface cần được mở rộng?

Khi GraphQL thực thi field của một object, runtime làm việc với object type cụ thể đã được xác định cho object đó. Trong schema, field coordinator được khai báo trên interface và được các object type triển khai. Spring for GraphQL hỗ trợ interface schema mapping bằng cách mở rộng mapping sang các object type triển khai interface.

Với batch mapping, cơ chế tương tự được áp dụng: khi một batch handler được ánh xạ tới interface field, Spring tạo mapping tương ứng cho từng object type triển khai interface. Nhờ vậy, một phương thức nhận danh sách Activity có thể xử lý các phần tử thuộc nhiều subtype.

Điều này giúp tránh việc viết cùng một logic batch riêng cho FooActivity và BarActivity nếu cả hai dùng chung quy tắc lấy coordinator. Khi một subtype mới triển khai Activity, mapping chung có thể được áp dụng cho subtype đó sau khi schema và type resolution được cấu hình hợp lệ.

## Model Java cho interface và các subtype

Phía Java có thể mô hình hóa hợp đồng Activity bằng một interface:

~~~java
public interface Activity {
    String id();
    String coordinatorId();
}

public record FooActivity(
        String id,
        String coordinatorId,
        String fooCode) implements Activity {
}

public record BarActivity(
        String id,
        String coordinatorId,
        String barCategory) implements Activity {
}

public record User(String id, String name) {
}
~~~

Các record giữ chung hai thuộc tính id và coordinatorId, đồng thời có dữ liệu riêng. Field coordinatorId là chi tiết của model Java dùng để tìm User; nó không bắt buộc phải xuất hiện trong GraphQL schema.

Query resolver có thể trả về danh sách interface:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;

    public ActivityController(ActivityService activityService) {
        this.activityService = activityService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findAll();
    }
}
~~~

Vì Query trả về interface, GraphQL runtime vẫn cần xác định object type thực tế của từng giá trị Java, ví dụ FooActivity hoặc BarActivity. Hãy bảo đảm type resolution của interface đã được cấu hình đúng. Phần batch mapping chỉ giải quyết việc tải field liên quan theo lô; nó không thay thế TypeResolver.

## Một @BatchMapping dùng chung cho interface

Spring for GraphQL cho phép khai báo batch handler trên interface field. Ví dụ:

~~~java
@Controller
public class ActivityBatchController {

    private final UserService userService;

    public ActivityBatchController(UserService userService) {
        this.userService = userService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> coordinatorIds = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> usersById =
                userService.findByIds(coordinatorIds);

        Map<Activity, User> result = new HashMap<>();
        for (Activity activity : activities) {
            result.put(
                    activity,
                    usersById.get(activity.coordinatorId()));
        }
        return result;
    }
}
~~~

Trong ví dụ, tên phương thức coordinator mặc định là tên field GraphQL. Kiểu phần tử của tham số List<Activity> cho Spring biết mapping thuộc interface Activity. Spring mở rộng mapping này sang các object type triển khai Activity, vì vậy batch handler có thể nhận một danh sách gồm FooActivity và BarActivity.

Phương thức lấy các coordinatorId duy nhất, gọi service một lần để tải các User rồi tạo map từ source Activity sang User tương ứng. Map dùng chính object source làm key, còn User là value. Với record, equals và hashCode được sinh dựa trên các thành phần record; nếu dùng class thông thường, cần bảo đảm key có equality ổn định để map tìm đúng source object.

Trong schema ví dụ, coordinator là nullable. Nếu một activity không có coordinator hoặc user tương ứng không tồn tại, map có thể chứa value null. Nếu hợp đồng schema đổi thành coordinator: User!, service phải bảo đảm mọi activity đều có User hợp lệ hoặc trả lỗi nghiệp vụ phù hợp.

## Cách Spring suy luận typeName và field

Khi không ghi thuộc tính trong @BatchMapping:

- Tên field mặc định được lấy từ tên phương thức.
- Tên type mặc định được suy ra từ kiểu phần tử của List source object.
- Nếu source type là một interface GraphQL, Spring mở rộng mapping tới các object type triển khai interface đó.

Có thể khai báo tường minh để làm rõ mapping:

~~~java
@BatchMapping(typeName = "Activity", field = "coordinator")
public Map<Activity, User> loadCoordinators(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

Ở đây tên Java method là loadCoordinators nhưng field GraphQL vẫn là coordinator. typeName chỉ rõ interface Activity. Dùng tên tường minh hữu ích khi tên method không trùng tên field hoặc khi controller chứa nhiều batch handler.

## Override mapping cho một subtype

Thông thường, một batch handler chung là đủ. Tuy nhiên, một subtype có thể cần quy tắc tải dữ liệu riêng. Ví dụ, FooActivity lấy coordinator từ hệ thống nội bộ, còn các subtype khác lấy từ UserService chung.

Có thể khai báo mapping chung rồi thay thế mapping cho subtype cụ thể:

~~~java
@Controller
public class ActivityBatchController {

    private final UserService userService;
    private final FooCoordinatorService fooCoordinatorService;

    public ActivityBatchController(
            UserService userService,
            FooCoordinatorService fooCoordinatorService) {
        this.userService = userService;
        this.fooCoordinatorService = fooCoordinatorService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        return userService.findCoordinators(activities);
    }

    @BatchMapping(field = "coordinator")
    public Map<FooActivity, User> fooCoordinators(
            List<FooActivity> activities) {
        return fooCoordinatorService.findFor(activities);
    }
}
~~~

Mapping thứ hai được suy luận cho FooActivity và field coordinator. Nó tiếp quản field của subtype này, trong khi mapping chung tiếp tục phục vụ các subtype còn lại. Cách này hữu ích khi một implementation có nguồn dữ liệu hoặc quy tắc nghiệp vụ khác biệt.

Khi override, hãy kiểm tra rằng chỉ có một handler chịu trách nhiệm cho cùng cặp type/field cụ thể. Hai mapping cạnh tranh cho cùng một tọa độ schema có thể gây lỗi khởi tạo hoặc hành vi không rõ ràng.

## Giá trị trả về: Map hoặc sequence đúng thứ tự

Batch mapping hỗ trợ hai cách trả kết quả phổ biến:

**Map từ source object tới value**

~~~java
@BatchMapping
public Map<Activity, User> coordinator(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

Map liên kết trực tiếp từng source object với value tương ứng. Thứ tự phần tử trong map không quan trọng, nhưng key phải khớp với source object. Nếu dùng Map key là object, hãy bảo đảm equals và hashCode ổn định.

**Flux có thứ tự tương ứng với source list**

~~~java
@BatchMapping
public Flux<User> coordinator(List<Activity> activities) {
    return userService.findCoordinatorsInOrder(activities);
}
~~~

Với Flux, sequence value phải có cùng số lượng và đúng thứ tự với danh sách source object đầu vào. Nếu đầu vào là [activity-1, activity-2, activity-3], các value phải lần lượt là coordinator của activity-1, activity-2 và activity-3. Không trả trực tiếp danh sách từ repository nếu repository không bảo đảm thứ tự đó.

Map thường dễ kiểm soát hơn khi service truy vấn theo tập ID và database trả kết quả theo thứ tự riêng. Flux hoặc collection theo thứ tự phù hợp khi service có thể tạo chính xác một value cho từng source object theo đúng vị trí.

## Batch mapping và DataLoader phía sau

@BatchMapping là cách viết gọn cho trường hợp phổ biến của DataLoader. Spring đăng ký batch function và tạo data fetcher cho field tương ứng. Data fetcher này lấy source object hiện tại, gọi DataLoader và trả kết quả cho GraphQL runtime.

Với interface Activity, Spring áp dụng mapping cho từng object type triển khai. Trong cùng một query, các lời gọi field coordinator của FooActivity và BarActivity có thể được gom theo mapping tương ứng để batch handler xử lý.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["Query activities"] --> B["List<Activity>"]
    B --> C["FooActivity"]
    B --> D["BarActivity"]
    C --> E["Field coordinator"]
    D --> F["Field coordinator"]
    E --> G["Batch mapping của interface Activity"]
    F --> G
    G --> H["Tải User theo nhóm ID"]
    H --> I["Map<Activity, User>"]
    I --> J["GraphQL response"]
~~~

Không cần tự tạo một DataLoader singleton. Spring quản lý registry và DataLoader theo GraphQL request, giúp cache không dùng chung giữa các request. Nếu cần dùng cùng loader ở nhiều resolver hoặc cần điều khiển key, context và cache chi tiết hơn, có thể đăng ký trực tiếp bằng BatchLoaderRegistry.

## Khi nào nên dùng BatchLoaderRegistry trực tiếp?

@BatchMapping phù hợp khi batch handler chỉ cần danh sách source object và context được hỗ trợ. Tuy nhiên, nếu logic cần đọc argument của field hoặc cần dữ liệu riêng từ từng lời gọi parent mapping, BatchLoaderRegistry trực tiếp thường phù hợp hơn.

Ví dụ client có thể yêu cầu coordinator theo locale:

~~~graphql
interface Activity {
  id: ID!
  coordinator(locale: String): User
}
~~~

Nếu mỗi activity có thể được gọi với argument locale khác nhau, một batch handler chỉ nhận List<Activity> không đủ để biểu diễn toàn bộ tổ hợp source object và argument. Có thể dùng @SchemaMapping nhận @Argument và gọi DataLoader với key tổng hợp:

~~~java
public record CoordinatorKey(String userId, String locale) {
}
~~~

Đăng ký mapped loader theo key tổng hợp:

~~~java
@Configuration
public class CoordinatorLoaderConfiguration {

    public CoordinatorLoaderConfiguration(
            BatchLoaderRegistry registry,
            UserService userService) {

        registry.forTypePair(CoordinatorKey.class, User.class)
                .registerMappedBatchLoader((keys, environment) ->
                        Mono.fromSupplier(() ->
                                userService.findByCoordinatorKeys(keys)));
    }
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Activity", field = "coordinator")
public CompletableFuture<User> coordinator(
        Activity activity,
        @Argument String locale,
        DataLoader<CoordinatorKey, User> coordinatorLoader) {
    return coordinatorLoader.load(
            new CoordinatorKey(activity.coordinatorId(), locale));
}
~~~

Trong trường hợp này, loader được đăng ký qua BatchLoaderRegistry với key CoordinatorKey và value User. Spring mở rộng interface schema mapping tới các object type triển khai, nên resolver có thể nhận Activity source object của từng subtype. Cần kiểm thử để xác nhận các resolver subtype cùng dùng đúng loader. Cách này cung cấp quyền kiểm soát key và argument cao hơn, đổi lại có thêm cấu hình.

## Giới hạn kích thước batch

Một batch quá lớn có thể tạo câu query chứa quá nhiều ID hoặc làm dịch vụ downstream chịu tải đột biến. @BatchMapping hỗ trợ thuộc tính maxBatchSize để giới hạn số source object trong mỗi batch:

~~~java
@BatchMapping(maxBatchSize = 100)
public Map<Activity, User> coordinator(List<Activity> activities) {
    return userService.findCoordinators(activities);
}
~~~

Nếu có 250 activity cần tải coordinator, Spring có thể chia thành nhiều batch không vượt quá giới hạn đã cấu hình. Chọn kích thước phù hợp với giới hạn truy vấn của database, API downstream và bộ nhớ. maxBatchSize không thay thế pagination của Query root; nó chỉ giới hạn kích thước mỗi lần batch loader được gọi.

## Bảo mật và context trong batch mapping

Batch handler có thể nhận thêm thông tin context được Spring hỗ trợ, chẳng hạn Principal, GraphQLContext, @ContextValue hoặc BatchLoaderEnvironment. Điều này hữu ích khi dữ liệu cần lọc theo tenant, người dùng hoặc quyền truy cập.

Ví dụ nhận tenant từ GraphQL context:

~~~java
@BatchMapping
public Map<Activity, User> coordinator(
        List<Activity> activities,
        @ContextValue("tenantId") String tenantId) {
    return userService.findCoordinators(activities, tenantId);
}
~~~

Tenant phải được thiết lập ở tầng request/interceptor và được xác thực từ principal đáng tin cậy. Không lấy tenantId trực tiếp từ field do client tự gửi rồi dùng nó làm ranh giới phân quyền. Batch query phải áp dụng cùng chính sách truy cập cho toàn bộ key trong batch.

Nếu một batch chứa source object thuộc các tenant khác nhau, service cần lọc theo tenant tương ứng cho từng key hoặc chia nhóm theo tenant trước khi truy vấn. Không được dùng một tenant context chung để trả dữ liệu của tenant khác.

## Xử lý dữ liệu thiếu và nullability

Khi batch handler trả Map, một source object không có key tương ứng sẽ được xem là không có value. Nếu map có key nhưng value là null, field cũng nhận null. Hành vi này phải phù hợp với nullability trong schema.

| Schema field | Khi không tìm thấy User |
| --- | --- |
| coordinator: User | Có thể trả null |
| coordinator: User! | Phải trả User hợp lệ hoặc phát sinh lỗi |

Nếu coordinator là non-null nhưng batch handler trả null, GraphQL tạo execution error và áp dụng null propagation. Hãy xác định dữ liệu thiếu là tình huống bình thường hay vi phạm domain. Nếu bình thường, schema nên cho phép null; nếu là lỗi dữ liệu, cần trả lỗi có ngữ nghĩa rõ ràng và ghi log phục vụ điều tra.

Không thay một User bị thiếu bằng một User bất kỳ chỉ để tránh null. Điều đó có thể khiến dữ liệu của activity bị gán nhầm và tạo lỗi nghiệp vụ khó phát hiện.

## Kiểm thử batch mapping trên interface

Kiểm thử cần có ít nhất hai implementation của interface trong cùng một kết quả Query:

~~~java
graphQlTester.document("""
        query {
            activities {
                id
                coordinator {
                    id
                    name
                }
                __typename
            }
        }
        """)
    .execute()
    .path("activities")
    .entityList(ActivityView.class)
    .hasSize(3);
~~~

Ngoài response, hãy kiểm tra batch service được gọi theo nhóm thay vì một lần cho mỗi source object. Những tình huống quan trọng gồm:

- Danh sách có nhiều subtype cùng triển khai interface.
- Một subtype override batch mapping chung.
- Nhiều source object có cùng coordinatorId.
- Repository trả User theo thứ tự khác với source list.
- Một source object không có User tương ứng.
- Batch vượt maxBatchSize và được chia thành nhiều lần gọi.
- Context tenant hoặc principal được áp dụng đúng.
- Một subtype mới triển khai interface vẫn nhận mapping chung.

Có thể dùng Mockito để xác minh số lần gọi service hoặc repository, nhưng nên có integration test với GraphQL runtime để xác nhận interface mapping được mở rộng đúng cho các object type thực tế.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Batch handler không chạy cho subtype | Type name hoặc field mapping không khớp interface SDL | Kiểm tra tên interface, field và object implements |
| Chỉ một implementation nhận kết quả | Mapping chỉ được đăng ký cho object type cụ thể | Khai báo batch mapping trên interface field |
| Subtype override không hoạt động | Tọa độ type/field hoặc tên method suy luận sai | Ghi rõ field và kiểm tra type suy luận từ List element |
| User bị gán nhầm Activity | Map key không khớp source object hoặc equals/hashCode không ổn định | Dùng source key ổn định và tạo map đúng |
| Flux trả sai quan hệ | Sequence value không cùng thứ tự source list | Sắp xếp lại value theo source list hoặc trả Map |
| Field nullable thành lỗi GraphQL | Schema khai báo non-null nhưng batch trả null | Điều chỉnh schema hoặc xử lý missing data đúng domain |
| Batch query quá lớn | Không giới hạn kích thước batch | Cấu hình maxBatchSize |
| Dữ liệu sai tenant | Batch handler bỏ qua context phân quyền | Truyền context đáng tin cậy và lọc theo tenant |

## Nguyên tắc thiết kế batch mapping trên interface

Khi xây dựng batch mapping cho interface, hãy áp dụng:

1. **Đặt field dùng chung trên interface.** Chỉ đưa vào hợp đồng những field có ý nghĩa với mọi implementation.
2. **Dùng một batch handler chung khi logic giống nhau.** Spring mở rộng mapping tới từng object type triển khai interface.
3. **Override subtype khi có quy tắc riêng.** Bảo đảm mỗi tọa độ type/field chỉ có một mapping có hiệu lực.
4. **Chọn Map khi cần ánh xạ tường minh.** Key phải là source object tương ứng; bảo đảm equals/hashCode ổn định.
5. **Chọn Flux khi giữ được thứ tự.** Value phải khớp số lượng và thứ tự source list.
6. **Dùng BatchLoaderRegistry khi cần argument hoặc key tùy chỉnh.** @BatchMapping không thay thế mọi trường hợp DataLoader nâng cao.
7. **Giới hạn kích thước batch.** Chọn maxBatchSize theo giới hạn của database và dịch vụ downstream.
8. **Bảo vệ dữ liệu theo context.** Áp dụng tenant và quyền truy cập cho từng key.
9. **Kiểm thử nhiều implementation.** Xác nhận mapping chung, override, missing value và số lần truy vấn.

Batch mapping trên interface cho phép một field chung được tải theo lô cho nhiều object type triển khai cùng hợp đồng. Spring for GraphQL mở rộng @BatchMapping trên interface tới các subtype, đồng thời cho phép override ở từng subtype khi cần. Khi chọn đúng source key, trả Map hoặc sequence đúng hợp đồng, kiểm soát nullability và context bảo mật, ứng dụng có thể giảm N+1 mà vẫn giữ kết quả nhất quán cho toàn bộ hệ thống đa hình.

## Tài liệu tham khảo

- [Spring for GraphQL - Annotated Controllers và Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
