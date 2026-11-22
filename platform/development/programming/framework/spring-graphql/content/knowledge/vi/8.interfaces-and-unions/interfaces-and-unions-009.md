# Interface batch mapping

Một GraphQL interface mô tả tập field chung mà nhiều object type cùng cung cấp. Ví dụ, hệ thống quản lý hoạt động có thể có nhiều loại hoạt động như hội thảo và buổi ra mắt sách. Tất cả đều có mã định danh, tiêu đề và người điều phối, nhưng mỗi loại còn có dữ liệu riêng.

Khi client truy vấn một danh sách interface và chọn field chung như `coordinator`, server cần phân giải field đó cho các object thuộc nhiều subtype. Nếu mỗi object tự tải coordinator bằng một truy vấn riêng, số lần truy cập database sẽ tăng theo số phần tử và tạo ra vấn đề N+1.

Spring for GraphQL hỗ trợ khai báo một `@BatchMapping` cho field của interface. Từ Spring for GraphQL 1.3, mapping này được tự động mở rộng thành mapping tương ứng cho từng object type triển khai interface. Cơ chế này áp dụng cho cả `@SchemaMapping` và `@BatchMapping`. Nhờ vậy, một batch resolver có thể tải dữ liệu liên quan cho nhiều subtype trong cùng một lần xử lý.

Bài học này giải thích cơ chế interface batch mapping, cách triển khai, cách ghi đè riêng subtype và cách kiểm thử việc batching trong Spring for GraphQL.

## 1. Interface và các object type triển khai

Interface định nghĩa một hợp đồng field chung. Object type triển khai interface phải cung cấp các field đó, đồng thời có thể bổ sung field riêng.

Ví dụ schema cho hoạt động:

~~~graphql
type Query {
  activities: [Activity!]!
}

interface Activity {
  id: ID!
  title: String!
  coordinator: User!
}

type WorkshopActivity implements Activity {
  id: ID!
  title: String!
  coordinator: User!
  room: String!
}

type BookLaunchActivity implements Activity {
  id: ID!
  title: String!
  coordinator: User!
  bookIsbn: String!
}

type User {
  id: ID!
  name: String!
}
~~~

Query có thể trả về danh sách chứa cả `WorkshopActivity` và `BookLaunchActivity`:

~~~graphql
query ActivityList {
  activities {
    id
    title
    coordinator {
      id
      name
    }
    ... on WorkshopActivity {
      room
    }
    ... on BookLaunchActivity {
      bookIsbn
    }
  }
}
~~~

Client chọn `coordinator` qua hợp đồng `Activity` mà không cần biết trước object cụ thể. Khi thực thi, GraphQL vẫn xử lý field trên object type thực tế của từng phần tử. Spring for GraphQL có thể ánh xạ một handler của interface thành các mapping cho từng object type triển khai nó.

## 2. Vấn đề N+1 khi phân giải field chung

Giả sử resolver gốc trả về 30 hoạt động:

~~~java
@QueryMapping
public List<Activity> activities() {
    return activityService.findAll();
}
~~~

Nếu mỗi lần phân giải `Activity.coordinator` đều gọi database riêng:

~~~java
@SchemaMapping
public User coordinator(Activity activity) {
    return userService.findById(activity.coordinatorId());
}
~~~

Server có thể thực hiện một truy vấn lấy danh sách hoạt động và thêm 30 truy vấn lấy coordinator. Đây là N+1: một truy vấn lấy tập cha, sau đó một truy vấn cho mỗi phần tử con.

Kết quả trả về có thể đúng nhưng chi phí I/O tăng theo số hoạt động. Khi danh sách lớn hoặc resolver gọi dịch vụ từ xa, độ trễ và tải hệ thống tăng đáng kể.

DataLoader giải quyết vấn đề bằng cách trì hoãn các lần tải riêng lẻ, gom key thành một batch và phân phối kết quả lại cho các lần gọi ban đầu. `@BatchMapping` là cách viết gọn cho trường hợp phổ biến này trong Spring for GraphQL.

## 3. Interface Batch Mapping hoạt động như thế nào?

Khi một controller method được ánh xạ vào field của schema interface, Spring for GraphQL mặc định thay mapping đó bằng nhiều mapping, mỗi mapping ứng với một object type triển khai interface.

Ví dụ:

- `Activity.coordinator` là field chung trong interface.
- `WorkshopActivity` triển khai `Activity`.
- `BookLaunchActivity` triển khai `Activity`.
- Một method `@BatchMapping` cho `Activity.coordinator` có thể phục vụ cả hai object type.

Spring đăng ký data fetcher tương ứng trên các concrete type. Khi GraphQL thực thi field `coordinator` trên các object cụ thể, data fetcher chuyển source object vào DataLoader và batch resolver nhận một nhóm source object để tải dữ liệu liên quan.

Hỗ trợ interface mapping được bổ sung trong Spring for GraphQL 1.3. Nếu ứng dụng dùng phiên bản cũ hơn, hãy kiểm tra khả năng hỗ trợ của phiên bản đó; có thể cần đăng ký mapping cho từng concrete type hoặc dùng `BatchLoaderRegistry` trực tiếp.

## 4. Xây dựng model Java cho các subtype

Java model có thể dùng một interface chung và các record triển khai nó:

~~~java
public interface Activity {

    String id();

    String title();

    String coordinatorId();
}
~~~

~~~java
public record WorkshopActivity(
        String id,
        String title,
        String coordinatorId,
        String room) implements Activity {
}
~~~

~~~java
public record BookLaunchActivity(
        String id,
        String title,
        String coordinatorId,
        String bookIsbn) implements Activity {
}
~~~

Record cung cấp `equals` và `hashCode` dựa trên các thành phần của record. Điều này hữu ích khi dùng source object làm key của Map trong kết quả batch. Nếu dùng class thông thường, hãy triển khai equality ổn định phù hợp với cách dùng key.

Kiểu người điều phối:

~~~java
public record User(String id, String name) {
}
~~~

Service của hoạt động có thể trả về danh sách gồm các implementation khác nhau nhưng cùng kiểu khai báo `List<Activity>`:

~~~java
@Service
public class ActivityService {

    public List<Activity> findAll() {
        return repository.findActivities();
    }
}
~~~

GraphQL cần xác định object type cụ thể khi một resolver trả về interface. Hãy cấu hình type resolver phù hợp hoặc dùng tên class trùng với tên GraphQL object type theo quy ước schema inspection của ứng dụng. Nếu tên Java và GraphQL khác nhau, đăng ký mapping tường minh bằng runtime wiring.

## 5. Viết @BatchMapping cho field của interface

Controller có thể khai báo một batch mapping nhận danh sách source object thuộc interface:

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
        return activityService.findAll();
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> coordinatorIds = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> usersById =
                userService.findAllByIds(coordinatorIds);

        return activities.stream().collect(Collectors.toMap(
                Function.identity(),
                activity -> Objects.requireNonNull(
                        usersById.get(activity.coordinatorId()),
                        "Coordinator must exist for activity " + activity.id())
        ));
    }
}
~~~

Trong ví dụ:

1. `@QueryMapping` trả về các object thuộc nhiều subtype của `Activity`.
2. `@BatchMapping` được ánh xạ tới field `coordinator` theo tên method.
3. Spring đăng ký batch loader và data fetcher dùng DataLoader cho field tương ứng.
4. Method nhận danh sách source object, thu thập các coordinator ID duy nhất và gọi service một lần.
5. Kết quả được trả về dưới dạng `Map<Activity, User>`, với mỗi activity là key và coordinator tương ứng là value.

Tên field mặc định được suy ra từ tên method là `coordinator`. Tên parent type được suy ra từ kiểu phần tử trong `List<Activity>`; ở đây là interface `Activity`. Có thể chỉ định tường minh nếu cần:

~~~java
@BatchMapping(typeName = "Activity", field = "coordinator")
public Map<Activity, User> loadCoordinators(List<Activity> activities) {
    // ...
}
~~~

Khi khai báo mapping trên interface, Spring for GraphQL mở rộng nó sang các object type triển khai interface. Do đó method không cần viết riêng cho từng subtype nếu logic tải dữ liệu giống nhau.

### Chọn kiểu trả về phù hợp

`@BatchMapping` hỗ trợ một số kiểu kết quả phổ biến:

| Kiểu trả về | Quy tắc |
| --- | --- |
| `Map<K, V>` | Map source object/key sang giá trị được tải |
| `Mono<Map<K, V>>` | Phiên bản reactive của mapped result |
| `List<V>` hoặc `Collection<V>` | Danh sách kết quả phải tương ứng theo thứ tự với danh sách source |
| `Flux<V>` | Chuỗi kết quả phải có cùng số lượng và đúng thứ tự source |

`Map` thường dễ kiểm tra hơn khi batch loader tải dữ liệu từ database bằng tập ID và thứ tự kết quả của database không được bảo đảm. Nếu dùng `List` hoặc `Flux`, method phải sắp xếp kết quả theo đúng thứ tự của danh sách source đầu vào.

Khi dùng source object làm key của Map, các object đó phải có `equals` và `hashCode` nhất quán. Không sửa các field tham gia equality sau khi đã dùng object làm key.

## 6. Ghi đè mapping cho một subtype cụ thể

Đôi khi các subtype có cách tải field chung khác nhau. Ví dụ, coordinator của workshop được lấy từ hệ thống nhân sự, còn coordinator của buổi ra mắt sách được lấy từ hệ thống sự kiện.

Có thể khai báo mapping mặc định cho interface rồi ghi đè mapping cho một subtype:

~~~java
@Controller
public class ActivityController {

    private final UserService userService;
    private final WorkshopService workshopService;

    public ActivityController(
            UserService userService,
            WorkshopService workshopService) {
        this.userService = userService;
        this.workshopService = workshopService;
    }

    @BatchMapping
    public Map<Activity, User> coordinator(List<Activity> activities) {
        Set<String> ids = activities.stream()
                .map(Activity::coordinatorId)
                .collect(Collectors.toSet());

        Map<String, User> users = userService.findAllByIds(ids);
        return activities.stream().collect(Collectors.toMap(
                Function.identity(),
                activity -> Objects.requireNonNull(
                        users.get(activity.coordinatorId()))
        ));
    }

    @BatchMapping(typeName = "WorkshopActivity", field = "coordinator")
    public Map<Activity, User> workshopCoordinators(
            List<WorkshopActivity> activities) {

        Set<String> ids = activities.stream()
                .map(WorkshopActivity::coordinatorId)
                .collect(Collectors.toSet());

        return workshopService.findCoordinators(ids);
    }
}
~~~

Mapping cụ thể cho `WorkshopActivity` được ưu tiên cho subtype đó; mapping interface vẫn phục vụ các subtype còn lại, ví dụ `BookLaunchActivity`. Cách này giúp giữ logic dùng chung và chỉ tách phần thật sự khác biệt.

Khi ghi đè, cần bảo đảm tên field và type name chính xác. Nếu mapping cụ thể trùng hoặc xung đột với mapping khác, ứng dụng có thể gặp lỗi đăng ký data fetcher khi khởi tạo schema.

## 7. Khi nào nên dùng BatchLoaderRegistry trực tiếp?

`@BatchMapping` phù hợp với trường hợp đơn giản: tải một field liên quan dựa trên danh sách parent object. Tuy nhiên, batch mapping method không nhận mọi tham số mà `@SchemaMapping` hỗ trợ. Nếu việc tải dữ liệu phụ thuộc vào arguments của field, local context riêng từng parent hoặc các tham số phức tạp khác, dùng `BatchLoaderRegistry` và `DataLoader` trực tiếp sẽ linh hoạt hơn.

Batch mapping method nhận danh sách source object và có thể nhận thêm `Principal`, `@ContextValue`, `GraphQLContext` hoặc `BatchLoaderEnvironment`. Nó không nhận `@Argument` như một schema mapping thông thường. Nếu cần giá trị argument, hãy để `@SchemaMapping` đọc argument rồi đưa dữ liệu ảnh hưởng kết quả vào DataLoader key.

Ví dụ schema có field filter:

~~~graphql
interface Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
}

type WorkshopActivity implements Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
  room: String!
}

type BookLaunchActivity implements Activity {
  id: ID!
  participantCount(includeGuests: Boolean = false): Int!
  bookIsbn: String!
}
~~~

Nếu số người tham gia cần thay đổi theo argument `includeGuests`, một batch loader chỉ nhận danh sách parent object sẽ không biết argument của từng field call. Có thể dùng `@SchemaMapping` nhận `@Argument` và gọi DataLoader với key chứa cả activity ID lẫn filter:

~~~java
public record ParticipantKey(
        String activityId,
        boolean includeGuests) {
}
~~~

~~~java
@Controller
public class ActivityParticipantController {

    @SchemaMapping(typeName = "Activity", field = "participantCount")
    public CompletableFuture<Integer> participantCount(
            Activity activity,
            @Argument boolean includeGuests,
            DataLoader<ParticipantKey, Integer> loader) {

        return loader.load(new ParticipantKey(
                activity.id(),
                includeGuests));
    }
}
~~~

Với interface mapping, method này có thể được mở rộng sang các subtype theo quy tắc của Spring for GraphQL. DataLoader key cần chứa mọi yếu tố làm thay đổi kết quả; nếu chỉ dùng activity ID, hai request cùng activity nhưng khác `includeGuests` có thể nhận nhầm kết quả cache.

Đăng ký mapped batch loader bằng `BatchLoaderRegistry`:

~~~java
registry.forTypePair(ParticipantKey.class, Integer.class)
        .registerMappedBatchLoader((keys, environment) ->
                participantService.countByKeys(keys));
~~~

Ở đây batch loader trả về số lượng người tham gia, nên value type là `Integer` và có thể đăng ký trực tiếp. Nếu field cần trả về collection, hãy dùng value wrapper có cách biểu diễn tương thích với kiểu GraphQL list và đăng ký DataLoader với generic type phù hợp; tránh dùng raw `List.class` rồi bỏ qua cảnh báo kiểu.

`BatchLoaderRegistry` hỗ trợ truy cập GraphQL context và context propagation. Spring Boot starter cung cấp registry dùng để đăng ký DataLoader theo request. Nên ưu tiên cơ chế này thay vì tự đăng ký DataLoader rời rạc nếu ứng dụng cần context propagation và quản lý vòng đời theo request.

## 8. Batching không đồng nghĩa một truy vấn SQL trong mọi trường hợp

Batch resolver nhận nhiều source object trong một lần gọi, nhưng số truy vấn thực tế phụ thuộc implementation của service và repository.

Ví dụ tốt:

~~~java
Map<String, User> usersById =
        userRepository.findAllById(coordinatorIds).stream()
                .collect(Collectors.toMap(User::id, Function.identity()));
~~~

Ví dụ vẫn tạo N+1 bên trong batch method:

~~~java
Map<Activity, User> result = new HashMap<>();
for (Activity activity : activities) {
    result.put(activity, userRepository.findById(
            activity.coordinatorId()).orElseThrow());
}
~~~

Trong ví dụ thứ hai, method chỉ được gọi một lần nhưng vẫn phát sinh một truy vấn cho mỗi activity. Hãy tải theo tập ID, dùng join/projection phù hợp hoặc gọi API hỗ trợ bulk lookup.

Batching cũng có giới hạn thực tế:

- Cơ sở dữ liệu có giới hạn số phần tử trong câu lệnh IN; chia batch thành các nhóm nhỏ khi cần.
- Dịch vụ ngoài có thể giới hạn số ID trong một request.
- Cần xử lý ID trùng lặp để tránh tải lặp lại không cần thiết.
- Kết quả thiếu key phải được xử lý rõ ràng, nhất là khi schema khai báo field non-null.
- Kích thước batch quá lớn có thể làm tăng bộ nhớ và thời gian xử lý.

`@BatchMapping` hỗ trợ thuộc tính `maxBatchSize` để giới hạn số parent keys trong một lần batch:

~~~java
@BatchMapping(maxBatchSize = 100)
public Map<Activity, User> coordinator(List<Activity> activities) {
    // Tải tối đa 100 activity trong một batch.
}
~~~

Nếu danh sách có 250 parent object, DataLoader có thể chia thành nhiều lần dispatch theo giới hạn đã cấu hình. Chọn giới hạn dựa trên khả năng của database hoặc service downstream và đo bằng dữ liệu thực tế.

## 9. Nullability và kết quả thiếu trong batch

Schema ví dụ khai báo:

~~~graphql
interface Activity {
  coordinator: User!
}
~~~

Field `coordinator` là non-null. Nếu batch loader không tìm thấy user cho một activity và trả về null, GraphQL tạo execution error và áp dụng null propagation theo schema. Nếu nghiệp vụ cho phép activity chưa có coordinator, schema nên biểu diễn điều đó bằng field nullable:

~~~graphql
interface Activity {
  coordinator: User
}
~~~

Nếu field non-null, batch loader nên phát hiện dữ liệu thiếu và xử lý theo quy tắc nghiệp vụ: báo lỗi có kiểm soát, sửa tính toàn vẹn dữ liệu hoặc dùng một đối tượng thay thế hợp lệ nếu domain cho phép. Không nên âm thầm gán một user mặc định không liên quan.

Khi dùng Map, key không có trong Map thường được DataLoader xem như không có kết quả tương ứng. Cần hiểu hành vi đó và bảo đảm phù hợp với nullability của schema. Với field nullable, null có thể là kết quả hợp lệ; với field non-null, null dẫn đến lỗi.

## 10. Cache và phạm vi của DataLoader

DataLoader thường được đăng ký và tạo cho từng GraphQL request. Nó có thể gom các lần load trùng key trong request và cache kết quả để tránh tải lặp. Cache này không thay thế cache dùng chung của ứng dụng hoặc cache database.

Một số nguyên tắc:

- Không lưu DataLoader request-scoped vào singleton field rồi tái sử dụng giữa các request.
- Key phải đại diện đầy đủ cho đầu vào ảnh hưởng đến kết quả.
- Nếu dữ liệu thay đổi trong cùng một mutation, cân nhắc clear hoặc prime key liên quan để tránh đọc lại giá trị cũ trong cùng request.
- Không dùng cache của DataLoader làm nguồn dữ liệu lâu dài.
- Đánh giá memory footprint nếu một query có thể tải số lượng entity rất lớn.

Với interface batch mapping, các subtype dùng chung field có thể đi qua các mapping đã được mở rộng. Điều này không có nghĩa mọi subtype phải dùng cùng một batch service; có thể ghi đè mapping cho subtype cụ thể hoặc dùng key và loader riêng khi có yêu cầu khác nhau.

## 11. Kiểm thử interface batch mapping

Nên kiểm tra cả response của interface query và việc service được gọi theo batch. Có thể dùng `@GraphQlTest` với controller và mock service:

~~~java
@GraphQlTest(ActivityController.class)
class ActivityControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    ActivityService activityService;

    @MockBean
    UserService userService;

    @Test
    void loadsCoordinatorForDifferentActivitySubtypes() {
        Activity workshop = new WorkshopActivity(
                "a-1", "Spring Workshop", "u-1", "Room A");
        Activity launch = new BookLaunchActivity(
                "a-2", "Book Launch", "u-2", "9780000000001");

        given(activityService.findAll())
                .willReturn(List.of(workshop, launch));
        given(userService.findAllByIds(Set.of("u-1", "u-2")))
                .willReturn(Map.of(
                        "u-1", new User("u-1", "An"),
                        "u-2", new User("u-2", "Bình")));

        graphQlTester.document("""
                query {
                    activities {
                        id
                        title
                        coordinator {
                            id
                            name
                        }
                        ... on WorkshopActivity {
                            room
                        }
                        ... on BookLaunchActivity {
                            bookIsbn
                        }
                    }
                }
                """)
                .execute()
                .path("activities[0].coordinator.name")
                .entity(String.class)
                .isEqualTo("An");

        then(userService).should()
                .findAllByIds(Set.of("u-1", "u-2"));
    }
}
~~~

Đây là ví dụ minh họa; cấu hình type resolver và mock cần phù hợp với model thực tế. Ngoài response, hãy kiểm tra:

- Batch method nhận source object từ cả hai subtype.
- Service bulk lookup được gọi một lần cho tập ID của batch.
- Kết quả coordinator được gắn đúng activity.
- Field riêng của mỗi subtype vẫn hoạt động qua inline fragment.
- Mapping ghi đè cho subtype được ưu tiên khi có khai báo cụ thể.
- Trường hợp thiếu coordinator tuân theo nullability của schema.
- Với batch trả về List hoặc Flux, thứ tự kết quả khớp thứ tự source object.

Để kiểm tra số lượng truy vấn database thực tế, dùng integration test với repository hoặc datasource spy/metrics. Một unit test chỉ verify service bulk method được gọi một lần chưa chứng minh database bên trong service chỉ chạy một câu SQL.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Batch method không được gọi | Field name hoặc type name không khớp schema | Kiểm tra tên interface, field và annotation attributes |
| Chỉ một subtype được batch | Mapping đang trỏ vào concrete type thay vì interface hoặc subtype khác chưa triển khai interface | Kiểm tra SDL và kiểu parent của method |
| Interface mapping không tự mở rộng | Phiên bản Spring for GraphQL cũ chưa hỗ trợ interface mapping | Kiểm tra phiên bản; khai báo mapping cho từng concrete type hoặc nâng cấp có kiểm soát |
| Hai resolver cùng tranh một field | Mapping interface và mapping subtype bị khai báo trùng không chủ ý | Chỉ ghi đè subtype khi có nhu cầu rõ ràng |
| Kết quả bị gán nhầm parent | Map key equality không ổn định hoặc dùng sai key | Dùng key immutable, equals/hashCode đúng hoặc trả sequence đúng thứ tự |
| Một batch vẫn chạy nhiều SQL | Service lặp query theo từng parent | Dùng bulk query theo tập ID |
| Một parent nhận kết quả của parent khác | DataLoader key thiếu yếu tố ảnh hưởng kết quả | Mở rộng key để bao gồm filter/tenant/locale liên quan |
| Non-null field phát sinh null error | Batch result thiếu giá trị bắt buộc | Kiểm tra dữ liệu, nullability và quy tắc lỗi |
| Batch method không nhận được argument filter | @BatchMapping không hỗ trợ mọi method argument của @SchemaMapping | Dùng @SchemaMapping gọi DataLoader và BatchLoaderRegistry |

## 13. Nguyên tắc thiết kế interface batch mapping

- Đặt field dùng chung trên interface khi mọi subtype có cùng ý nghĩa và hợp đồng dữ liệu.
- Dùng một `@BatchMapping` trên interface khi các subtype có thể được tải theo cùng một quy tắc.
- Ghi đè mapping trên concrete type khi subtype có nguồn dữ liệu hoặc quy tắc nghiệp vụ riêng.
- Dùng Map keyed by source object khi thứ tự kết quả từ repository không ổn định; bảo đảm key có equals/hashCode ổn định.
- Dùng List/Flux chỉ khi có thể bảo đảm thứ tự kết quả khớp tuyệt đối với source list.
- Dùng `BatchLoaderRegistry` khi cần key phức hợp, field arguments hoặc logic context chi tiết.
- Giữ DataLoader trong phạm vi request và thiết kế key đủ phân biệt kết quả.
- Đo truy vấn database thực tế; batch annotation không tự bảo đảm chỉ có một truy vấn.
- Thiết kế nullability nhất quán với khả năng dữ liệu thực tế.
- Kiểm thử tất cả subtype, mapping override và trường hợp dữ liệu thiếu.

## 14. Bài tập thực hành

Xây dựng API cho các loại hoạt động:

1. Khai báo interface `Activity` có `id`, `title` và `coordinator`.
2. Tạo `WorkshopActivity` và `BookLaunchActivity` triển khai interface.
3. Tạo query trả về danh sách `Activity` gồm cả hai subtype.
4. Viết một `@BatchMapping` cho field `coordinator` trên interface.
5. Dùng service bulk lookup để tải tất cả user theo coordinator ID.
6. Ghi đè mapping cho `WorkshopActivity` để tải coordinator từ service riêng.
7. Viết test GraphQlTester xác nhận hai subtype đều có coordinator đúng.
8. Đo số truy vấn SQL trước và sau khi batch mapping.
9. Thử thay field `coordinator: User!` thành nullable và kiểm tra hành vi khi thiếu user.

Khi hoàn thành, hãy giải thích được vì sao mapping trên interface có thể được Spring mở rộng cho các subtype, DataLoader gom các lần tải ra sao, khi nào cần ghi đè mapping cụ thể và vì sao một batch method vẫn có thể gây N+1 nếu service bên trong tiếp tục truy vấn từng parent.

## 15. Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers: Interface Batch Mappings](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4.2 — BatchMapping API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL 1.3 RC1 — Schema Interface Mapping](https://spring.io/blog/2024/04/16/spring-for-graphql-1-3-rc1-released/)

Phiên bản Spring for GraphQL và GraphQL Java quyết định một số chi tiết API. Khi nâng cấp, hãy kiểm tra Javadoc đúng phiên bản, đặc biệt với interface mapping, chữ ký controller method và các kiểu reactive return.
