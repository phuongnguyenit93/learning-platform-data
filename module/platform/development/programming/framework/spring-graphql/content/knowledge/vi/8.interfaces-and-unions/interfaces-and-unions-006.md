# Interface mapping trong controller

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách GraphQL interface mô tả các field dùng chung cho nhiều object type.
- Trả về danh sách các kiểu triển khai interface từ một Query trong Spring for GraphQL.
- Dùng một phương thức controller để mapping field của interface cho tất cả kiểu triển khai.
- Ghi đè mapping chung cho một subtype cụ thể khi có logic riêng.
- Phân biệt interface field mapping với việc xác định concrete type bằng TypeResolver.
- Dùng inline fragment và __typename để truy vấn dữ liệu theo từng subtype.
- Cân nhắc @BatchMapping khi field chung cần tải dữ liệu liên quan theo lô.

## 1. Interface trong GraphQL giải quyết vấn đề gì?

Một API có thể trả về nhiều loại đối tượng nhưng các loại đó cùng chia sẻ một số field. Ví dụ, hệ thống quản lý hoạt động có nhiều loại hoạt động như hội thảo, cuộc họp và buổi đào tạo. Tất cả đều có mã định danh và người điều phối, nhưng mỗi loại có thêm thông tin riêng.

Nếu không có interface, schema có thể lặp lại các field chung trên từng object type. GraphQL interface cho phép khai báo hợp đồng chung và yêu cầu các object type triển khai hợp đồng đó.

Ví dụ:

~~~graphql
interface Activity {
  id: ID!
  coordinator: User!
}

type Workshop implements Activity {
  id: ID!
  coordinator: User!
  topic: String!
}

type Meeting implements Activity {
  id: ID!
  coordinator: User!
  room: String!
}

type User {
  id: ID!
  name: String!
}
~~~

Trong schema này:

- Activity khai báo hai field chung: id và coordinator.
- Workshop và Meeting phải cung cấp các field được yêu cầu bởi Activity.
- Workshop có thêm topic.
- Meeting có thêm room.

Interface giúp client truy vấn danh sách Activity mà không cần biết trước từng object type cụ thể. Khi cần dữ liệu riêng, client có thể dùng inline fragment để yêu cầu field của subtype.

## 2. Khai báo Java model cho các subtype

Ở phía Java, có thể biểu diễn interface GraphQL bằng một Java interface chung và các class triển khai.

~~~java
public interface Activity {
    String getId();
    String getCoordinatorId();
}

public class Workshop implements Activity {

    private final String id;
    private final String coordinatorId;
    private final String topic;

    public Workshop(
            String id,
            String coordinatorId,
            String topic) {
        this.id = id;
        this.coordinatorId = coordinatorId;
        this.topic = topic;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public String getCoordinatorId() {
        return coordinatorId;
    }

    public String getTopic() {
        return topic;
    }
}

public class Meeting implements Activity {

    private final String id;
    private final String coordinatorId;
    private final String room;

    public Meeting(
            String id,
            String coordinatorId,
            String room) {
        this.id = id;
        this.coordinatorId = coordinatorId;
        this.room = room;
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public String getCoordinatorId() {
        return coordinatorId;
    }

    public String getRoom() {
        return room;
    }
}
~~~

Java interface giúp service và controller xử lý các subtype thông qua cùng một abstraction. Các class cụ thể vẫn giữ field riêng của từng loại.

Service có thể trả về danh sách hỗn hợp:

~~~java
public List<Activity> findActivities() {
    return List.of(
            new Workshop("w-01", "u-01", "GraphQL basics"),
            new Meeting("m-01", "u-02", "Room A")
    );
}
~~~

Một điểm quan trọng: Java interface và GraphQL interface là hai cơ chế riêng. Việc Java class implements một interface không tự động làm GraphQL biết object đó tương ứng với concrete GraphQL type nào. GraphQL runtime vẫn cần xác định kiểu object thực tế khi field trả về một interface.

## 3. Query trả về interface trong Spring for GraphQL

Khai báo Query trong SDL:

~~~graphql
type Query {
  activities: [Activity!]!
}
~~~

Controller có thể trả về danh sách Java interface:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;

    public ActivityController(ActivityService activityService) {
        this.activityService = activityService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findActivities();
    }
}
~~~

Phương thức activities được ánh xạ tới field Query.activities. Giá trị trả về là List<Activity>, trong đó từng phần tử thực tế có thể là Workshop hoặc Meeting.

Khi GraphQL thực thi field activities, engine cần biết concrete type của từng phần tử để tiếp tục phân giải các field được chọn. Đó là trách nhiệm của abstract type resolution, thường được cấu hình bằng TypeResolver hoặc cơ chế suy luận kiểu mặc định phù hợp với tên class.

## 4. Mapping một field chung cho mọi subtype

Đây là điểm quan trọng của interface mapping trong annotated controller.

Giả sử interface Activity có field coordinator. Mỗi subtype đều có coordinatorId và cần tải User tương ứng. Nếu tạo một resolver riêng cho Workshop và một resolver khác cho Meeting, logic có thể bị lặp lại.

Spring for GraphQL hỗ trợ ánh xạ một controller method vào field của schema interface. Theo mặc định, mapping đó được thay thế bằng các mapping tương ứng cho từng object type triển khai interface.

Controller:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;
    private final UserService userService;

    public ActivityController(
            ActivityService activityService,
            UserService userService) {
        this.activityService = activityService;
        this.userService = userService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findActivities();
    }

    @SchemaMapping
    public User coordinator(Activity activity) {
        return userService.findById(activity.getCoordinatorId());
    }
}
~~~

Vì tham số source có kiểu Java Activity và tên phương thức là coordinator, Spring suy ra mapping cho field coordinator của schema interface Activity.

Spring for GraphQL mở rộng mapping interface này thành mapping cho từng object type triển khai Activity, ví dụ Workshop.coordinator và Meeting.coordinator. Do đó, cùng một phương thức được gọi cho mọi subtype phù hợp.

Có thể hình dung quá trình như sau:

~~~mermaid
flowchart TD
    A[Query activities] --> B[List<Activity>]
    B --> C[Workshop]
    B --> D[Meeting]
    C --> E[Workshop.coordinator]
    D --> F[Meeting.coordinator]
    E --> G[coordinator(Activity)]
    F --> G
    G --> H[UserService]
    H --> I[User]
~~~

Điều này đặc biệt hữu ích khi field chung có cùng ý nghĩa và cùng cách xử lý trên mọi subtype. Controller chỉ cần một phương thức, trong khi GraphQL runtime đăng ký mapping cho các object type cụ thể.

### Khi nào cần khai báo typeName tường minh?

Nếu tên Java interface không trùng tên GraphQL interface hoặc muốn tránh phụ thuộc vào quy ước suy luận, có thể khai báo rõ type name:

~~~java
@SchemaMapping(typeName = "Activity", field = "coordinator")
public User resolveCoordinator(Activity activity) {
    return userService.findById(activity.getCoordinatorId());
}
~~~

Trong ví dụ này:

- typeName xác định GraphQL interface là Activity.
- field xác định field cần mapping là coordinator.
- Tham số Activity là source object được đưa vào phương thức.

Tên field có thể được suy ra từ tên phương thức nếu bỏ thuộc tính field. Tên type có thể được suy ra từ kiểu source nếu kiểu Java khớp với GraphQL interface.

## 5. Ghi đè mapping cho một subtype cụ thể

Có trường hợp field chung cần cách xử lý khác trên một subtype. Ví dụ, Workshop lấy coordinator từ dịch vụ nhân sự, còn Meeting dùng coordinator được lưu trong một nguồn lịch họp riêng.

Bạn có thể khai báo một mapping chung cho interface và một mapping cụ thể cho subtype:

~~~java
@Controller
public class ActivityController {

    private final UserService userService;
    private final MeetingService meetingService;

    public ActivityController(
            UserService userService,
            MeetingService meetingService) {
        this.userService = userService;
        this.meetingService = meetingService;
    }

    @SchemaMapping
    public User coordinator(Activity activity) {
        return userService.findById(activity.getCoordinatorId());
    }

    @SchemaMapping
    public User coordinator(Meeting meeting) {
        return meetingService.findCoordinator(meeting.getId());
    }
}
~~~

Mapping nhận Activity áp dụng cho các subtype nói chung, ngoại trừ subtype đã có mapping cụ thể. Mapping nhận Meeting được dùng riêng cho Meeting.

Quy tắc này cho phép dùng chung hành vi mặc định và chỉ tùy biến nơi thực sự cần. Khi thêm một subtype mới triển khai Activity, mapping chung vẫn có thể phục vụ field coordinator của subtype đó.

Hãy giữ tên field và kiểu trả về tương thích với SDL. Nếu một subtype có cách biểu diễn khác hẳn hoặc field không còn mang cùng ý nghĩa nghiệp vụ, hãy xem xét thiết kế schema thay vì cố ép mọi trường hợp vào một resolver chung.

## 6. Truy vấn interface và inline fragment

Client có thể truy vấn các field chung trực tiếp trên interface. Để lấy field riêng của từng subtype, dùng inline fragment.

Ví dụ:

~~~graphql
query ActivityList {
  activities {
    __typename
    id
    coordinator {
      id
      name
    }
    ... on Workshop {
      topic
    }
    ... on Meeting {
      room
    }
  }
}
~~~

Trong query:

- id và coordinator là field được khai báo trên interface Activity.
- __typename trả về tên concrete GraphQL type của từng phần tử.
- ... on Workshop chỉ yêu cầu topic khi phần tử là Workshop.
- ... on Meeting chỉ yêu cầu room khi phần tử là Meeting.

Response minh họa:

~~~json
{
  "data": {
    "activities": [
      {
        "__typename": "Workshop",
        "id": "w-01",
        "coordinator": {
          "id": "u-01",
          "name": "Lan"
        },
        "topic": "GraphQL basics"
      },
      {
        "__typename": "Meeting",
        "id": "m-01",
        "coordinator": {
          "id": "u-02",
          "name": "Minh"
        },
        "room": "Room A"
      }
    ]
  }
}
~~~

__typename rất hữu ích cho client khi cần render giao diện theo từng subtype, cache dữ liệu theo concrete type hoặc xử lý các nhánh dữ liệu khác nhau.

## 7. TypeResolver và concrete type resolution

Interface chỉ mô tả những field mà các object type cùng hỗ trợ. Khi resolver trả về một Java object, GraphQL vẫn cần xác định object đó là Workshop hay Meeting.

Nếu tên Java class và tên GraphQL object type phù hợp với quy ước suy luận mặc định của Spring for GraphQL, cơ chế ClassNameTypeResolver có thể xác định concrete type. Nếu tên không tương ứng, hoặc ứng dụng dùng nhiều loại object Java phức tạp, hãy khai báo TypeResolver rõ ràng.

Ví dụ:

~~~java
@Bean
RuntimeWiringConfigurer activityTypeResolver() {
    return wiringBuilder -> wiringBuilder.type(
            "Activity",
            typeBuilder -> typeBuilder.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source instanceof Workshop) {
                    return environment.getSchema()
                            .getObjectType("Workshop");
                }

                if (source instanceof Meeting) {
                    return environment.getSchema()
                            .getObjectType("Meeting");
                }

                throw new IllegalStateException(
                        "Unsupported Activity type: "
                                + source.getClass().getName());
            })
    );
}
~~~

TypeResolver chỉ chịu trách nhiệm chọn concrete GraphQL object type. Nó không tải field coordinator và không thay thế các phương thức @SchemaMapping.

Phân biệt hai việc:

| Thành phần | Trách nhiệm |
|---|---|
| TypeResolver | Xác định object Java hiện tại là GraphQL type cụ thể nào |
| @SchemaMapping | Lấy giá trị cho một field của object type |
| @QueryMapping | Lấy dữ liệu cho field thuộc Query |
| @BatchMapping | Tải dữ liệu liên quan cho nhiều source object theo lô |

Nếu TypeResolver trả về sai object type, các field riêng trong inline fragment có thể không được thực thi như mong đợi. Nếu TypeResolver đúng nhưng thiếu mapping cho field cần tải từ nguồn riêng, field đó vẫn có thể trả null hoặc không có dữ liệu như dự kiến.

## 8. Dùng @BatchMapping cho field chung của interface

Field coordinator trong ví dụ trước có thể tạo ra N+1 nếu mỗi Activity gọi UserService riêng. Khi danh sách có nhiều hoạt động, resolver coordinator có thể được gọi một lần cho mỗi phần tử.

Spring for GraphQL hỗ trợ interface batch mapping. Tương tự interface schema mapping, một phương thức @BatchMapping gắn với field của interface được mở rộng thành các mapping cho object type triển khai interface.

Ví dụ:

~~~java
@Controller
public class ActivityController {

    private final ActivityService activityService;
    private final UserService userService;

    public ActivityController(
            ActivityService activityService,
            UserService userService) {
        this.activityService = activityService;
        this.userService = userService;
    }

    @QueryMapping
    public List<Activity> activities() {
        return activityService.findActivities();
    }

    @BatchMapping
    public Mono<Map<Activity, User>> coordinator(
            List<Activity> activities) {

        List<String> userIds = activities.stream()
                .map(Activity::getCoordinatorId)
                .distinct()
                .toList();

        return userService.findAllByIds(userIds)
                .collectMap(
                        User::getId,
                        Function.identity()
                )
                .map(usersById -> {
                    Map<Activity, User> result = new HashMap<>();

                    for (Activity activity : activities) {
                        User user = usersById.get(
                                activity.getCoordinatorId());
                        result.put(activity, user);
                    }

                    return result;
                });
    }
}
~~~

Phương thức nhận danh sách source object và trả về map từ từng Activity sang User tương ứng. Spring đăng ký batch loader và DataFetcher cho field coordinator.

Ví dụ giả định UserService.findAllByIds trả về Flux<User> và mọi Activity đều có coordinator tương ứng. Vì SDL khai báo coordinator là User!, nếu có thể thiếu User thì cần xử lý trường hợp đó trong nghiệp vụ hoặc đổi field thành nullable.

Khi dùng source object làm key của Map, các object cần có equals và hashCode ổn định để được dùng làm khóa duy nhất. Nếu model không có equality phù hợp, có thể cân nhắc cách batch khác dựa trên khóa định danh hoặc dùng BatchLoaderRegistry và DataLoader tường minh.

Một lựa chọn khác là trả về Flux<User>, nhưng thứ tự phần tử trả về phải khớp chính xác thứ tự danh sách source object đầu vào. Nếu không bảo đảm được thứ tự, hãy dùng Map để liên kết kết quả với source object rõ ràng.

Không phải field interface nào cũng cần batch mapping. Nếu dữ liệu đã có sẵn trong source object hoặc chỉ cần một phép tính nhẹ, PropertyDataFetcher hay @SchemaMapping đơn giản có thể đủ. Chỉ dùng batch khi field phải tải dữ liệu liên quan cho nhiều parent object và cần giảm số lần gọi nguồn dữ liệu.

## 9. Kiểm thử interface mapping

Kiểm thử cần xác nhận cả mapping chung, mapping ghi đè và concrete type resolution.

Ví dụ với GraphQlTester:

~~~java
@Test
void shouldResolveCommonAndSubtypeFields() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                activities {
                    __typename
                    id
                    coordinator {
                        name
                    }
                    ... on Workshop {
                        topic
                    }
                    ... on Meeting {
                        room
                    }
                }
            }
            """)
            .execute();

    response.path("activities[0].__typename")
            .entity(String.class)
            .isEqualTo("Workshop");

    response.path("activities[0].coordinator.name")
            .entity(String.class)
            .isEqualTo("Lan");

    response.path("activities[0].topic")
            .entity(String.class)
            .isEqualTo("GraphQL basics");

    response.path("activities[1].__typename")
            .entity(String.class)
            .isEqualTo("Meeting");

    response.path("activities[1].room")
            .entity(String.class)
            .isEqualTo("Room A");
}
~~~

Các tình huống nên kiểm thử:

1. Query trả về nhiều subtype trong cùng một danh sách interface.
2. Field chung như id và coordinator được resolve cho tất cả subtype.
3. Inline fragment chỉ trả field thuộc subtype tương ứng.
4. __typename phản ánh đúng concrete GraphQL type.
5. Mapping chung được sử dụng cho subtype chưa có mapping riêng.
6. Mapping cụ thể ghi đè mapping chung đúng subtype.
7. TypeResolver từ chối hoặc xử lý rõ object Java không được hỗ trợ.
8. Batch mapping trả kết quả đúng cho từng source object, kể cả khi thiếu bản ghi liên quan.

Ngoài test resolver, nên có integration test dùng schema SDL thực tế. Điều này giúp phát hiện trường hợp Java model có vẻ đúng nhưng GraphQL schema không khai báo field, subtype không implements interface hoặc type resolver không tìm được object type.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field chung không chạy trên subtype | Interface mapping không được phát hiện hoặc type name không khớp | Kiểm tra source argument và typeName |
| Field riêng không xuất hiện | Client chưa dùng inline fragment hoặc SDL không khai báo field | Kiểm tra fragment và object type |
| Abstract type không resolve được | TypeResolver không xác định được concrete type | Kiểm tra mapping giữa Java class và GraphQL object type |
| Subtype dùng sai resolver | Mapping cụ thể chưa được khai báo hoặc không khớp type | Khai báo @SchemaMapping cho source subtype |
| Nhiều lần gọi UserService | Field mapping thực hiện truy vấn từng parent object | Dùng @BatchMapping hoặc DataLoader |
| Batch result gắn nhầm parent | Map key không ổn định hoặc Flux sai thứ tự | Dùng key equality ổn định hoặc bảo đảm thứ tự |
| Field chung bị lặp code | Mỗi subtype tự khai báo cùng logic | Đưa mapping lên interface nếu ngữ nghĩa thực sự giống nhau |

## 11. Nguyên tắc thiết kế interface mapping

Khi thiết kế controller cho GraphQL interface, hãy lưu ý:

- Đặt các field có cùng ý nghĩa nghiệp vụ trên interface.
- Dùng Java interface hoặc abstraction phù hợp để controller nhận source object chung.
- Tạo một @SchemaMapping cho field chung khi tất cả subtype dùng cùng logic.
- Tạo mapping riêng cho subtype khi cần hành vi khác biệt.
- Đảm bảo GraphQL xác định được concrete type thông qua TypeResolver hoặc cơ chế mặc định.
- Dùng inline fragment để truy vấn field đặc thù.
- Dùng __typename khi client cần phân biệt subtype.
- Cân nhắc @BatchMapping cho field chung cần tải dữ liệu liên quan theo lô.
- Kiểm thử trường hợp nhiều subtype cùng xuất hiện trong một response.

Không nên đưa một field lên interface chỉ vì các subtype tình cờ có cùng tên. Field chung cần có cùng ngữ nghĩa và hợp đồng. Nếu hai subtype có quy tắc dữ liệu khác nhau đáng kể, mapping riêng thường dễ hiểu và an toàn hơn.

## Kết luận

Spring for GraphQL hỗ trợ mapping field của GraphQL interface trực tiếp trong annotated controller. Một phương thức @SchemaMapping nhận source Java interface có thể được mở rộng thành mapping cho từng object type triển khai interface. Khi cần, controller có thể khai báo mapping riêng cho một subtype để ghi đè hành vi chung.

Interface mapping kết hợp với TypeResolver, inline fragment và __typename giúp API trả về nhiều kiểu object qua một hợp đồng thống nhất. Với field chung cần tải dữ liệu liên quan, @BatchMapping còn giúp gom việc truy xuất theo lô và giảm N+1. Thiết kế đúng ranh giới giữa field chung và field riêng sẽ giúp schema dễ mở rộng và controller dễ bảo trì.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers, Interface Schema Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Batch Loading, Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.batch-mapping)
- [Spring for GraphQL — Schema Mapping Annotation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)
