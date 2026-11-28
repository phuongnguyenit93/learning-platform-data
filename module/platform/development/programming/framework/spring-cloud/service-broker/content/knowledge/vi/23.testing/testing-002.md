# Kiểm thử đơn vị CatalogService và các quy tắc gói dịch vụ

Catalog là hợp đồng đầu tiên mà nền tảng đọc khi kết nối tới Open Service Broker. Từ catalog, platform biết broker cung cấp service nào, mỗi service có plan nào, plan có bindable hay không và những metadata/schema nào mô tả cách sử dụng. Nếu catalog sai, platform có thể không hiển thị dịch vụ, cho phép một thao tác không được hỗ trợ hoặc gửi request với plan không phù hợp.

Trong module SPRING_CLOUD_SERVICE_BROKER, CatalogService cần được kiểm thử như một phần của API contract và như nơi công bố chính sách dịch vụ. Unit test nên xác nhận cả cấu trúc catalog lẫn các quy tắc nghiệp vụ của plan: định danh ổn định, khả năng provision/bind, visibility, giới hạn tính năng, schema parameters và tính nhất quán giữa catalog với application service. Bài này dùng JUnit 5, Mockito và Reactor StepVerifier làm ví dụ; tên model/builder cụ thể cần khớp phiên bản Spring Cloud Open Service Broker mà dự án sử dụng.

## 1. Vai trò của catalog trong OSB

Nền tảng thường lấy catalog từ endpoint:

~~~http
GET /v2/catalog
X-Broker-API-Version: 2.17
Authorization: Basic ...
~~~

Broker trả về danh sách service definitions và plans. Một service definition thường mô tả:

- ID ổn định và tên hiển thị.
- Description và metadata.
- Danh sách plan được cung cấp.
- Service có cho phép binding hay không.
- Những capability liên quan như plan update, instances sharing hoặc route/volume binding nếu broker hỗ trợ.
- Schema đầu vào cho provisioning và binding nếu có công bố.

Một plan mô tả biến thể dịch vụ mà platform có thể chọn, ví dụ Basic, Standard hoặc High Availability. Plan thường có ID, tên, mô tả, free flag, metadata và schema parameters. Platform dùng các thông tin này để hiển thị lựa chọn và xây dựng request; broker vẫn phải kiểm tra plan ở mọi thao tác thực tế.

Catalog không phải nơi thay thế authorization hoặc validation. Việc một plan xuất hiện trong catalog không chứng minh caller có quyền sử dụng plan đó, và việc parameters được mô tả trong schema không loại bỏ việc broker phải validate lại khi nhận request.

## 2. Mục tiêu của unit test CatalogService

Một bộ test có ích cần trả lời:

1. Catalog có đúng số service và plan mà broker dự định công bố không?
2. Mỗi service/plan có ID ổn định, duy nhất và tên/description hợp lệ không?
3. Bindability và các capability có khớp với implementation không?
4. Metadata có đúng kiểu dữ liệu và chứa thông tin cần thiết không?
5. Schema parameters có mô tả đúng input được chấp nhận không?
6. Plan bị ẩn, ngừng bán hoặc không khả dụng có bị loại khỏi catalog theo policy không?
7. Catalog có deterministic giữa các lần gọi không?
8. Publisher có phát đúng một catalog rồi complete, hoặc phát lỗi rõ ràng khi cấu hình hỏng không?
9. Plan ID/service ID từ catalog có được các application service nhận diện nhất quán không?

Không nên chỉ kiểm tra Mono không null hoặc list có ít nhất một phần tử. Những assertion đó có thể pass dù platform nhận sai plan ID, plan bị thiếu hoặc capability bị công bố nhầm.

## 3. Tách catalog model khỏi nguồn cấu hình

Trong ứng dụng thực tế, catalog có thể được xây dựng từ code, YAML configuration, database hoặc một catalog registry. Nên tách phần đọc cấu hình, validation và mapping sang model OSB.

Ví dụ một mô hình nội bộ:

~~~java
public record ServicePlanConfig(
        String id,
        String name,
        String description,
        boolean free,
        boolean bindable,
        boolean enabled,
        int maxStorageGb,
        int maxReplicas) {
}

public record ServiceConfig(
        String id,
        String name,
        String description,
        boolean bindable,
        List<ServicePlanConfig> plans) {
}
~~~

Đây là cấu trúc cấu hình do ứng dụng định nghĩa, không phải model OSB. Catalog assembler nhận các cấu hình đã validate, áp dụng visibility policy rồi tạo model ServiceDefinition/Plan của framework. Cách tách này giúp test quy tắc nghiệp vụ mà không cần khởi động toàn bộ Spring context.

CatalogService có thể trả Mono<Catalog> theo extension point của framework:

~~~java
@Service
public class BrokerCatalogService implements CatalogService {

    private final CatalogAssembler assembler;

    public BrokerCatalogService(CatalogAssembler assembler) {
        this.assembler = assembler;
    }

    @Override
    public Mono<Catalog> getCatalog() {
        return Mono.fromSupplier(assembler::buildCatalog);
    }
}
~~~

Đây là ví dụ theo kiểu API thường gặp của Spring Cloud Open Service Broker. Nếu phiên bản dependency có chữ ký hoặc model khác, dùng interface thực tế từ dependency thay vì sao chép ví dụ một cách máy móc.

## 4. Kiểm thử cấu trúc catalog cơ bản

Test đầu tiên xác nhận catalog có service mong đợi và không rỗng:

~~~java
@ExtendWith(MockitoExtension.class)
class BrokerCatalogServiceTest {

    @Mock
    CatalogAssembler assembler;

    @InjectMocks
    BrokerCatalogService catalogService;

    @Test
    void returnsCatalogFromAssembler() {
        Catalog expected = Catalog.builder()
                .serviceDefinitions(List.of(testServiceDefinition()))
                .build();
        when(assembler.buildCatalog()).thenReturn(expected);

        StepVerifier.create(catalogService.getCatalog())
                .assertNext(actual -> {
                    assertThat(actual.getServiceDefinitions())
                            .hasSize(1);
                    assertThat(actual.getServiceDefinitions().get(0).getId())
                            .isEqualTo("postgres-service");
                })
                .verifyComplete();

        verify(assembler).buildCatalog();
    }
}
~~~

Test này xác nhận đường đi từ assembler tới publisher. Tuy nhiên, nó chưa kiểm tra assembler tạo catalog đúng. Cần có test riêng cho assembler và một contract test cho model cuối cùng.

Nếu CatalogAssembler là dependency blocking hoặc build catalog tốn nhiều thời gian, cân nhắc khởi tạo catalog một lần khi startup và trả một object immutable. Không nên để mỗi request GET catalog gọi nhiều dịch vụ từ xa nếu catalog không cần thay đổi theo từng request.

## 5. Kiểm thử service definition và plan identity

ID service và plan là định danh mà platform lưu lại rồi gửi trong các request provision/update/bind. Vì vậy, ID cần ổn định giữa các lần deploy. Không tạo ID bằng tên hiển thị, random UUID mỗi lần build hoặc index của phần tử trong list.

Các assertion nên có:

- Service ID không rỗng và duy nhất trong catalog.
- Plan ID không rỗng và duy nhất trong phạm vi service theo quy tắc broker.
- Tên hiển thị và description không rỗng nếu contract nội bộ yêu cầu.
- Plan thuộc đúng service.
- Thay đổi label hoặc description không làm thay đổi ID.
- Thứ tự catalog deterministic nếu platform hoặc snapshot test phụ thuộc thứ tự.

Ví dụ:

~~~java
@Test
void serviceAndPlanIdsAreStableAndUnique() {
    Catalog catalog = assembler.buildCatalog();

    assertThat(catalog.getServiceDefinitions())
            .extracting(ServiceDefinition::getId)
            .doesNotHaveDuplicates()
            .contains("postgres-service");

    ServiceDefinition service = findService(catalog, "postgres-service");

    assertThat(service.getPlans())
            .extracting(Plan::getId)
            .doesNotHaveDuplicates()
            .contains("basic", "ha");
}
~~~

Nếu dùng builder API khác, điều chỉnh accessor theo model thực tế. Điều cần kiểm tra là ID contract, không phải chi tiết implementation của builder.

## 6. Kiểm thử quy tắc bindable

Bindability có thể được công bố ở service definition và/hoặc ở plan tùy mô hình API, framework version và cách broker thiết kế. Test phải bảo đảm catalog không tuyên bố một khả năng mà implementation không hỗ trợ.

Ví dụ:

| Service/plan policy | Catalog kỳ vọng | Application behavior |
|---|---|---|
| Service cho phép bind | Service definition công bố bindable | Binding service triển khai create/unbind |
| Service không cho bind | bindable=false | Request bind bị từ chối |
| Plan chỉ hỗ trợ provision, không cấp credentials | Capability được mô tả đúng theo framework contract | Không trả binding credentials |
| Plan yêu cầu app context | Catalog/schema/capability công bố đúng yêu cầu | Binding handler kiểm tra context |

Không giả định field bindable ở plan luôn có cùng ý nghĩa với field bindable ở service. Kiểm tra model và contract của phiên bản OSB/framework đang dùng. Unit test cần xác nhận mapping từ domain policy sang field framework; integration test xác nhận platform nhận được JSON đúng.

Một test cho service không bindable:

~~~java
@Test
void nonBindableServiceIsPublishedAsNonBindable() {
    ServiceDefinition definition =
            assembler.toServiceDefinition(configWithBindingDisabled());

    assertThat(definition.isBindable()).isFalse();
}
~~~

Test phía application service cũng phải xác nhận request bind vào service không bindable bị từ chối trước khi gọi provider adapter. Nếu chỉ test catalog, broker có thể công bố đúng nhưng handler vẫn cho phép bind do thiếu guard nghiệp vụ.

## 7. Kiểm thử quy tắc plan

Plan thường quyết định giới hạn tài nguyên, tính năng và giá. Một số quy tắc điển hình:

| Quy tắc | Ví dụ | Assertion |
|---|---|---|
| Plan ID ổn định | basic, standard, ha | ID không phụ thuộc display name |
| Plan enabled | ha đang được bán | Plan xuất hiện trong catalog |
| Plan disabled | legacy không nhận instance mới | Plan không được công bố theo visibility policy |
| Giới hạn storage | Basic tối đa 100 GB | 101 GB bị từ chối |
| Giới hạn replica | Standard tối đa 2 replica | 3 replica bị từ chối |
| Feature entitlement | Backup nâng cao chỉ có ở HA | Basic không được bật feature |
| Free flag | Basic miễn phí, HA tính phí | Metadata/free flag phản ánh đúng cấu hình |
| Update policy | Chỉ cho phép nâng plan | Hạ plan bị từ chối nếu policy không cho phép |
| Binding policy | Plan cho phép tối đa N binding | Binding thứ N+1 bị từ chối |

Test nên đặt ranh giới:

- Giá trị nhỏ nhất được phép.
- Giá trị lớn nhất được phép.
- Giá trị thấp hơn min một đơn vị.
- Giá trị cao hơn max một đơn vị.
- Giá trị null hoặc thiếu.
- Sai kiểu dữ liệu.
- Giá trị âm, zero hoặc số quá lớn.

Ví dụ:

~~~java
@ParameterizedTest
@CsvSource({
        "1, true",
        "100, true",
        "0, false",
        "101, false",
        "-1, false"
})
void validatesStorageAgainstPlanLimit(
        int storageGb, boolean expected) {

    PlanPolicy basic = new PlanPolicy(1, 100, 2);

    assertThat(basic.acceptsStorage(storageGb))
            .isEqualTo(expected);
}
~~~

Không chỉ test giá trị hợp lệ. Lỗi thường xuất hiện ở ranh giới max, khi conversion từ JSON number sang Integer/Long hoặc khi giá trị thiếu được gán default không đúng.

## 8. Kiểm thử schema parameters

OSB cho phép broker công bố schema cho parameters ở service/plan. Schema giúp platform tạo form và validation phía client; broker vẫn phải kiểm tra server-side khi nhận request.

Ví dụ schema provision:

~~~json
{
  "parameters": {
    "type": "object",
    "properties": {
      "storageGb": {
        "type": "integer",
        "minimum": 1,
        "maximum": 100
      },
      "backupEnabled": {
        "type": "boolean",
        "default": false
      }
    },
    "additionalProperties": false
  }
}
~~~

Test schema nên xác nhận:

- Required fields đúng với use case.
- Type đúng: integer không bị công bố thành string.
- Min/max khớp PlanPolicy.
- Enum values chỉ gồm giá trị backend hỗ trợ.
- Default không làm thay đổi ý nghĩa nghiệp vụ ngoài dự kiến.
- additionalProperties phản ánh chính sách unknown parameters.
- Schema binding và schema provisioning không bị tráo.
- Plan có giới hạn khác nhau thì schema cũng phản ánh đúng plan đó.

Không chỉ snapshot JSON schema rồi coi như đã test policy. Cần test validator thực tế với cùng bộ boundary cases để bảo đảm schema và server-side validation không lệch nhau.

## 9. Kiểm thử metadata

Metadata có thể được platform dùng để hiển thị display name, bullets, costs, documentation URL, support URL hoặc thông tin tùy chọn khác theo contract. Metadata phải có kiểu dữ liệu đúng và không chứa bí mật.

Một số kiểm tra:

- Display name/description là chuỗi dễ hiểu.
- Cost là cấu trúc dữ liệu đúng schema mà platform mong đợi.
- Documentation/support URL thuộc domain tin cậy.
- Không có internal hostname, private endpoint hoặc credential.
- Metadata không chứa tenant-specific value nếu catalog là chung cho mọi caller.
- Metadata của plan không mâu thuẫn với service definition.

Nếu catalog có nội dung theo tenant hoặc authorization context, test phải xác định rõ catalog có được phép thay đổi theo caller không. Không cache catalog dùng chung nếu kết quả có dữ liệu nhạy cảm hoặc visibility khác nhau theo tenant.

## 10. Kiểm thử plan visibility và lifecycle

Plan có thể ở các trạng thái như enabled, deprecated, hidden hoặc retired trong domain model. Cần phân biệt:

- Plan không còn nhận instance mới.
- Plan vẫn tồn tại để hiển thị và hỗ trợ instance cũ.
- Plan không còn được công bố trong catalog.
- Plan không còn được phép dùng trong update.

Không nên dùng một boolean enabled cho mọi ý nghĩa nếu policy thực tế cần nhiều trạng thái. Ví dụ plan deprecated có thể vẫn xuất hiện trong catalog với metadata cảnh báo nhưng không cho provision mới. Một plan retired có thể bị ẩn khỏi catalog nhưng broker vẫn phải hiểu plan ID cũ khi deprovision instance đã tồn tại.

Bộ test nên kiểm tra:

| Plan lifecycle | Catalog | Provision mới | Update instance cũ | Deprovision |
|---|---|---|---|---|
| ACTIVE | Hiển thị | Cho phép theo policy | Cho phép theo policy | Cho phép |
| DEPRECATED | Hiển thị hoặc cảnh báo theo policy | Có thể từ chối hoặc cho phép trong grace period | Theo migration policy | Cho phép |
| HIDDEN | Không hiển thị với catalog public | Theo policy; thường không nhận mới | Có thể cần cho instance cũ | Cho phép |
| RETIRED | Không hiển thị | Từ chối | Từ chối hoặc yêu cầu migrate | Vẫn phải xử lý instance cũ |

Đây là ví dụ domain policy, không phải trạng thái chuẩn bắt buộc của OSB. Hành vi cuối cùng phải được định nghĩa rõ trong broker và kiểm thử nhất quán ở catalog lẫn handlers.

## 11. Kiểm thử CatalogService reactive

Nếu CatalogService trả Mono<Catalog>, dùng StepVerifier để xác nhận signal:

~~~java
@Test
void emitsOneCatalogAndCompletes() {
    when(assembler.buildCatalog()).thenReturn(testCatalog());

    StepVerifier.create(catalogService.getCatalog())
            .assertNext(catalog ->
                    assertThat(catalog.getServiceDefinitions())
                            .isNotEmpty())
            .verifyComplete();
}
~~~

Kiểm thử lỗi:

~~~java
@Test
void propagatesInvalidCatalogConfiguration() {
    when(assembler.buildCatalog())
            .thenThrow(new InvalidCatalogConfigurationException());

    StepVerifier.create(catalogService.getCatalog())
            .expectError(InvalidCatalogConfigurationException.class)
            .verify();
}
~~~

Nếu implementation dùng Mono.defer hoặc fromSupplier, exception xảy ra khi subscribe và StepVerifier có thể quan sát nó. Nếu build catalog ngay trong constructor hoặc khi Spring startup, lỗi có thể xảy ra trước khi test subscribe; chọn thời điểm validation có chủ đích.

Catalog thông thường là dữ liệu cấu hình ít thay đổi. Có thể build và validate khi application startup để fail fast, sau đó phục vụ một object immutable. Nếu catalog được tải động, cần kiểm tra cache invalidation, refresh atomic và hành vi khi nguồn cấu hình unavailable.

Không tự subscribe trong CatalogService. Framework sẽ subscribe publisher để tạo HTTP response. Test cũng nên dùng StepVerifier thay vì gọi subscribe rồi kiểm tra biến mutable.

## 12. Kiểm thử lỗi cấu hình và dữ liệu trùng

Catalog không nên được công bố một phần khi cấu hình sai. Một số lỗi cần phát hiện:

- Service ID trùng.
- Plan ID trùng trong cùng service.
- Plan tham chiếu service không tồn tại.
- Plan thiếu name/description bắt buộc.
- Max storage nhỏ hơn min storage.
- Replica limit bằng zero hoặc âm.
- Plan enabled nhưng backend adapter chưa được cấu hình.
- Service bindable nhưng binding service chưa được triển khai.
- Schema có enum/default không hợp lệ.
- URL metadata dùng scheme hoặc host không được phép.

Nên validate toàn bộ catalog trước khi publish. Nếu catalog được tải từ database, build snapshot mới rồi swap atomically; không để platform đọc nửa catalog cũ, nửa catalog mới.

Ví dụ test cấu hình trùng:

~~~java
@Test
void rejectsDuplicatePlanIds() {
    ServiceConfig config = configWithDuplicatePlanIds("basic");

    assertThatThrownBy(() -> validator.validate(config))
            .isInstanceOf(InvalidCatalogConfigurationException.class)
            .hasMessageContaining("duplicate plan id");
}
~~~

Thông báo lỗi startup có thể chứa service/plan ID để operator sửa cấu hình, nhưng không nên chứa credentials hoặc secret.

## 13. Kiểm thử tính nhất quán giữa catalog và handlers

Một lỗi thực tế là catalog công bố plan ID ha, nhưng provision handler chỉ chấp nhận high-availability; hoặc catalog nói bindable=true nhưng binding handler luôn từ chối.

Tạo một contract fixture dùng chung cho catalog tests và application-service tests:

1. Đọc catalog được build.
2. Lấy service ID và plan ID công bố.
3. Gửi command provision với đúng định danh đó.
4. Xác nhận plan resolver tìm được cùng PlanPolicy.
5. Kiểm tra parameters trong schema được validator chấp nhận.
6. Kiểm tra một giá trị ngoài schema bị từ chối.
7. Nếu service công bố bindable, xác nhận binding use case được bật theo policy.

Không nhất thiết phải gọi cloud provider thật. Dùng fake adapter hoặc mock ở ranh giới hạ tầng, nhưng giữ nguyên catalog assembler, plan resolver và validator thật để kiểm tra tính nhất quán.

## 14. Unit test, slice test và contract test

Phân chia test theo mục tiêu:

| Loại test | Thành phần | Mục tiêu |
|---|---|---|
| Unit test | PlanPolicy, CatalogValidator, CatalogAssembler | Quy tắc nghiệp vụ và mapping |
| Unit test | BrokerCatalogService | Publisher trả đúng catalog và signal |
| Repository test | Catalog/plan repository | Query, uniqueness và mapping persistence |
| Spring slice/context test | Bean wiring và configuration properties | Framework nhận đúng CatalogService và config |
| HTTP contract test | GET /v2/catalog | JSON response đúng OSB schema và status |
| Integration test | Platform-facing flow với application service | Catalog ID/plan thực sự dùng được ở provision/bind |

Unit test nên nhanh, không cần khởi động toàn bộ application context. Một vài context/HTTP contract test có giá trị để xác minh Spring wiring và serialization. Không cần lặp lại cùng một assertion ở mọi tầng.

## 15. Ví dụ bộ test cho CatalogAssembler

Một lớp test assembler có thể tập trung vào mapping và plan rules:

~~~java
@ExtendWith(MockitoExtension.class)
class CatalogAssemblerTest {

    @Mock
    CatalogConfiguration configuration;

    @Mock
    CatalogValidator validator;

    @InjectMocks
    CatalogAssembler assembler;

    @Test
    void publishesOnlyVisiblePlansWithStableIds() {
        when(configuration.services()).thenReturn(List.of(
                postgresWithPlans(
                        plan("basic", true),
                        plan("legacy", false))));

        Catalog catalog = assembler.buildCatalog();

        ServiceDefinition service =
                findService(catalog, "postgres-service");

        assertThat(service.getPlans())
                .extracting(Plan::getId)
                .containsExactly("basic");
        verify(validator).validate(configuration.services());
    }
}
~~~

Đây là pseudocode minh họa; cấu trúc config và cách mock cần điều chỉnh theo constructor thật. Nếu CatalogAssembler chỉ nhận config bất biến và không có dependency ngoài, có thể không cần Mockito; tạo config trực tiếp sẽ làm test đơn giản và rõ hơn.

## 16. Test data builder và fixture

Catalog/plan model thường có nhiều field. Tạo fixture builder để giảm lặp, nhưng tránh builder test che mất giá trị đang được kiểm tra.

Ví dụ:

~~~java
private static ServicePlanConfig plan(
        String id, boolean enabled) {
    return new ServicePlanConfig(
            id,
            id.toUpperCase(Locale.ROOT),
            "Plan " + id,
            false,
            true,
            enabled,
            100,
            2);
}
~~~

Khi test min/max, hãy override rõ field liên quan trong test thay vì dựa vào default ẩn trong fixture. Fixture không nên chứa giá trị production secret hoặc endpoint thật. Dùng domain giả lập như example.test và resource ID tổng hợp.

Nếu catalog có nhiều service, đặt tên fixture theo mục đích như bindableService, nonBindableService, deprecatedPlan và planAtStorageLimit. Tên fixture giúp đọc test mà không phải mở helper để hiểu.

## 17. Kiểm thử deterministic catalog và cache

GET catalog có thể được platform gọi nhiều lần. Nếu catalog được build từ map hoặc nguồn dữ liệu không có thứ tự, thứ tự service/plan có thể thay đổi giữa các request. Điều này gây snapshot noise và có thể làm khó debug.

Test nên xác nhận:

- Cùng cấu hình tạo cùng service/plan IDs.
- Thứ tự được sắp xếp theo quy tắc xác định nếu contract của broker yêu cầu deterministic ordering.
- Hai lần gọi không tạo ID ngẫu nhiên hoặc metadata thời gian khác nhau.
- Cache trả snapshot nhất quán.
- Refresh catalog thay toàn bộ snapshot atomically.
- Lỗi refresh không xóa catalog đang hoạt động nếu policy yêu cầu giữ bản cuối đã validate.

Không cache một catalog chứa thông tin riêng theo caller trong một cache global. Nếu catalog thực sự phụ thuộc tenant/authorization, cache key phải bao gồm scope thích hợp và dữ liệu nhạy cảm phải được tách riêng.

## 18. Kiểm thử serialization của catalog

Model Java đúng chưa đủ; JSON serialize sai field hoặc sai cấu trúc vẫn làm platform hiểu nhầm. HTTP contract test nên kiểm tra:

- Top-level có service definitions theo schema OSB.
- Service ID, name, description và bindable serialize đúng.
- Plan list nằm dưới đúng service.
- Metadata và schemas dùng đúng cấu trúc.
- Boolean không bị serialize thành string.
- Số giới hạn không bị serialize sai kiểu.
- Field optional bị lược bỏ hoặc null đúng theo framework contract.
- Không có field nội bộ như database password, provider credential hoặc private endpoint.

Dùng WebTestClient hoặc MockMvc tùy stack web/reactive của ứng dụng. Với broker reactive, WebTestClient phù hợp để gọi endpoint và kiểm tra JSON path. Không chỉ so sánh raw JSON snapshot nếu serializer có thể thay đổi thứ tự key; ưu tiên assertion theo JSON path/structure.

## 19. Bộ kiểm thử gợi ý

Một ma trận gọn có thể bắt đầu như sau:

| Nhóm | Test quan trọng |
|---|---|
| Service identity | ID ổn định, duy nhất, không rỗng |
| Plan identity | ID duy nhất trong service, mapping đúng |
| Visibility | Disabled/hidden/deprecated theo policy |
| Bindability | Catalog field khớp binding implementation |
| Plan limits | Min/max storage, replica, connection và binding count |
| Features | Feature entitlement theo plan |
| Schema | Type, required, enum, default, additionalProperties |
| Metadata | Display, costs, docs/support URL, không chứa secret |
| Reactive behavior | Value, complete, error; không phát nhiều catalog |
| Configuration failure | Duplicate ID, invalid limit, missing adapter |
| Consistency | Plan từ catalog được resolver và provision handler chấp nhận |
| Serialization | JSON contract GET /v2/catalog |
| Cache/refresh | Snapshot ổn định và refresh atomic |

Không cần tạo hàng trăm test cho mọi tổ hợp. Dùng parameterized test cho các boundary values và chọn các ca đại diện cho từng loại policy. Các quy tắc có rủi ro cao như plan visibility, bindability, quota và ID compatibility nên có test riêng dễ đọc.

## 20. Những sai lầm thường gặp

- Chỉ kiểm tra catalog không rỗng.
- Dùng display name làm service ID hoặc plan ID.
- Sinh ID ngẫu nhiên mỗi lần build catalog.
- Công bố plan/capability mà handler chưa triển khai.
- Chỉ kiểm tra schema mà không test server-side validator.
- Dùng một PlanPolicy cho mọi plan dù giới hạn khác nhau.
- Coi plan disabled, deprecated, hidden và retired là cùng một trạng thái.
- Dùng mock cho assembler trong mọi test nên không kiểm tra mapping thật.
- Chỉ unit test model mà không kiểm tra JSON endpoint.
- Cache catalog có dữ liệu theo tenant mà không scope cache key.
- Nuốt lỗi cấu hình rồi trả catalog thiếu service/plan.
- Đưa endpoint nội bộ hoặc secret vào metadata.

## Kết luận

Unit test CatalogService cần bảo vệ catalog như một contract mà platform sử dụng để khám phá service và plan. Hãy kiểm tra định danh ổn định, metadata, bindability, visibility, schema và các giới hạn của từng plan; đồng thời bảo đảm những gì catalog công bố khớp với validator và handlers thực tế. JUnit 5 và Mockito phù hợp để kiểm tra mapping/policy, StepVerifier kiểm tra signal của Mono, còn WebTestClient hoặc MockMvc xác nhận JSON OSB ở HTTP boundary. Kết hợp unit test nhanh với một số contract/integration test có trọng điểm giúp phát hiện sớm catalog sai, plan không dùng được và capability bị công bố vượt quá khả năng triển khai của service broker Spring Cloud.
