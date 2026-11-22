# Kiểm tra hành vi khi cờ bật và khi cờ tắt

Feature flag (cờ tính năng) cho phép thay đổi hành vi của ứng dụng mà không nhất thiết phải phát hành một binary mới. Cùng một artifact có thể phục vụ người dùng theo hai nhánh logic: nhánh hiện tại khi cờ tắt và nhánh mới khi cờ bật. Cách phát hành này hỗ trợ triển khai dần, thử nghiệm có kiểm soát và tắt nhanh một tính năng khi phát hiện sự cố.

Tuy nhiên, một feature flag tạo ra nhiều trạng thái mà pipeline phải kiểm tra. Nếu chỉ test nhánh bật, hệ thống có thể làm hỏng hành vi đang dùng khi cờ tắt. Nếu chỉ test nhánh tắt, code mới có thể chưa từng được thực thi trước khi bật cho người dùng. Cấu hình targeting, giá trị mặc định, lỗi khi lấy trạng thái cờ và chuyển trạng thái trong lúc ứng dụng đang chạy cũng có thể gây lỗi.

**Kiểm tra cả khi cờ bật và khi cờ tắt** là xác minh hai nhánh hành vi theo hợp đồng của tính năng, đồng thời kiểm tra những điều kiện khiến ứng dụng chọn mỗi nhánh. Mục tiêu là bảo đảm tính năng mới hoạt động đúng khi được bật, hành vi hiện tại vẫn được giữ khi tắt và hệ thống có thể chuyển đổi an toàn trong vòng đời phát hành.

## 1. Feature flag thay đổi điều gì?

Feature flag là một quyết định runtime hoặc cấu hình có thể điều khiển việc một đoạn hành vi được thực thi. Ví dụ:

- Release toggle: triển khai code trước, bật tính năng sau khi đã sẵn sàng.
- Experiment toggle: chia người dùng vào các biến thể để đo lường.
- Operational toggle: tắt một chức năng tốn tài nguyên khi hệ thống chịu tải cao.
- Permission/entitlement toggle: quyết định người dùng hoặc nhóm nào được sử dụng chức năng.
- Kill switch: ngừng nhanh một hành vi có rủi ro khi xảy ra sự cố.

Không phải mọi loại cờ đều có cùng ngữ nghĩa. Một cờ dùng để mở tính năng mới có thể mặc định tắt; một cờ điều khiển chế độ an toàn có thể cần mặc định bật. Giá trị mặc định phải được xác định theo rủi ro và hành vi an toàn của ứng dụng, không áp dụng máy móc quy tắc “mọi cờ đều false”.

Ví dụ, dịch vụ đơn hàng có thể thêm luồng tính giá mới:

```java
public Price calculate(Order order, EvaluationContext context) {
    if (featureFlags.isEnabled("new-pricing", context, false)) {
        return newPricing.calculate(order);
    }
    return legacyPricing.calculate(order);
}
```

Khi cờ tắt, ứng dụng dùng cách tính giá cũ. Khi cờ bật, ứng dụng dùng bộ tính giá mới. Cả hai nhánh đều là hành vi cần được kiểm tra trong cùng phiên bản artifact.

## 2. Xác định hợp đồng của từng trạng thái

Trước khi viết test, cần mô tả rõ ứng dụng phải làm gì trong từng trạng thái:

| Trạng thái | Hành vi cần xác minh |
|---|---|
| Flag OFF | Giữ hành vi hiện tại; không kích hoạt side effect chỉ thuộc tính năng mới |
| Flag ON | Thực hiện hành vi mới theo yêu cầu; dữ liệu và kết quả đúng |
| Flag không tồn tại | Dùng giá trị mặc định đã định nghĩa và có hành vi an toàn |
| Flag provider không truy cập được | Áp dụng fallback theo policy; không làm ứng dụng lỗi ngoài dự kiến |
| Flag có giá trị không hợp lệ | Không diễn giải tùy tiện; dùng fallback và ghi nhận lỗi cấu hình |
| User không thuộc cohort | Không bật tính năng cho user đó |
| User thuộc cohort | Bật đúng biến thể hoặc hành vi được chỉ định |

Hợp đồng cần nêu rõ cả kết quả quan sát được lẫn tác dụng phụ. Ví dụ, khi cờ tắt, API response có thể vẫn theo schema cũ, không phát event mới và không ghi dữ liệu vào bảng chỉ phục vụ tính năng mới. Khi cờ bật, response và event phải tuân theo contract mới.

Với cờ nhiều trạng thái như control, treatment-a, treatment-b, không nên ép chúng thành Boolean trong thiết kế test. Hãy kiểm tra từng biến thể được hỗ trợ và hành vi fallback khi giá trị không nhận diện được.

## 3. Test nhánh OFF: bảo vệ hành vi hiện tại

Nhánh OFF thường bị xem nhẹ vì tính năng mới chưa được bật. Nhưng trong giai đoạn triển khai dần, phần lớn người dùng có thể vẫn chạy nhánh này. Một lỗi trong nhánh OFF có thể ảnh hưởng toàn bộ người dùng hiện tại.

Các điều cần kiểm tra:

- Kết quả nghiệp vụ giống hợp đồng trước khi thêm feature flag.
- API response, status code và schema không thay đổi ngoài dự kiến.
- Không gọi service hoặc API chỉ cần cho tính năng mới.
- Không ghi event, message hoặc dữ liệu mới nếu nhánh OFF không được phép tạo chúng.
- Không thay đổi thứ tự xử lý, transaction hoặc quy tắc tính toán cũ.
- Không yêu cầu dependency mới chỉ được dùng ở nhánh ON nếu nhánh OFF không cần nó.
- Logging và metric không tạo lỗi hoặc tiết lộ dữ liệu nhạy cảm.

Không chỉ kiểm tra rằng kết quả trả về khác hay giống nhau. Hãy kiểm tra các side effect quan trọng như số lần gọi gateway, database write, message publish và audit event. Ví dụ, khi cờ tắt, luồng cũ có thể phải tiếp tục dùng payment provider hiện tại và không gửi yêu cầu sang provider mới.

Một cách mạnh để bảo vệ nhánh OFF là dùng characterization/regression tests: lưu lại các trường hợp đầu vào và kết quả hợp lệ của hành vi cũ trước khi thay đổi, sau đó chạy lại chúng khi cờ OFF.

## 4. Test nhánh ON: xác minh tính năng mới đầy đủ

Nhánh ON cần được kiểm tra theo acceptance criteria của tính năng. Không nên dừng ở việc xác nhận code branch được thực thi.

Các khía cạnh thường cần kiểm tra:

- Kết quả nghiệp vụ với đầu vào hợp lệ, biên và không hợp lệ.
- Quyền truy cập và điều kiện đủ tư cách sử dụng.
- Tích hợp với database, API, message broker hoặc dịch vụ bên ngoài.
- Validation, error handling, timeout và retry.
- Event hoặc side effect được tạo đúng một lần và đúng nội dung.
- Khả năng tương thích với dữ liệu cũ và dữ liệu mới.
- Metric, log và trace có đủ thông tin để theo dõi tính năng.
- Hiệu năng và tài nguyên khi lượng người dùng được bật tăng lên.

Với ví dụ tính giá, nhánh ON cần kiểm tra quy tắc chiết khấu, làm tròn, tiền tệ, thuế, lỗi khi không lấy được bảng giá và tính nhất quán giữa giá hiển thị với giá ghi nhận trong đơn hàng.

Nếu tính năng mới dùng API hoặc schema mới, cần test cả trường hợp dependency chưa sẵn sàng. Không giả định rằng cờ ON đồng nghĩa mọi dependency đã hoạt động hoàn hảo.

## 5. Kiểm tra giá trị mặc định và khi flag provider lỗi

Feature flag có thể được lấy từ file cấu hình, environment, SDK hoặc dịch vụ quản lý cờ từ xa. Trong thực tế, cấu hình có thể thiếu, provider có thể timeout hoặc trả về giá trị không hợp lệ.

Test cần trả lời:

- Nếu flag chưa được khai báo, ứng dụng dùng giá trị nào?
- Nếu SDK chưa khởi tạo xong, hành vi có an toàn không?
- Nếu dịch vụ flag tạm thời không truy cập được, ứng dụng dùng cached value hay default?
- Cached value cũ được phép dùng trong bao lâu?
- Nếu cấu hình đổi kiểu dữ liệu hoặc sai tên biến thể, ứng dụng xử lý thế nào?
- Nếu provider phục hồi, ứng dụng có nhận giá trị mới đúng cách không?

Fallback phụ thuộc loại flag. Với release toggle cho tính năng mới, mặc định OFF thường là lựa chọn an toàn để giữ hành vi đã biết. Với kill switch có nghĩa “cho phép chức năng nguy hiểm”, default cần được thiết kế theo nguyên tắc fail-safe, có thể là tắt chức năng khi không xác định được trạng thái. Nhưng một cờ điều khiển bảo vệ khác có thể cần default ON. Tài liệu của từng flag phải giải thích lựa chọn này.

Không nên để lỗi flag provider làm toàn bộ ứng dụng ngừng phục vụ nếu có thể dùng fallback an toàn. Ngược lại, không được âm thầm bật tính năng mới khi không đọc được cấu hình nếu điều đó làm tăng rủi ro nghiệp vụ.

## 6. Kiểm tra targeting và rollout theo cohort

Nhiều hệ thống không bật cờ cho tất cả người dùng cùng lúc. Cờ có thể được targeting theo user ID, tenant, region, plan, nhóm nội bộ hoặc phần trăm traffic.

Các trường hợp nên kiểm tra:

- Người dùng thuộc cohort được bật nhận đúng hành vi mới.
- Người dùng ngoài cohort tiếp tục nhận hành vi cũ.
- User/tenant ID thiếu hoặc không hợp lệ được xử lý theo default.
- Quy tắc ưu tiên giữa các điều kiện targeting hoạt động đúng.
- Một user giữ nguyên nhóm trong các lần request nếu policy yêu cầu phân nhóm ổn định.
- Tỷ lệ rollout thay đổi không làm user liên tục đổi nhánh ngoài ý muốn.
- Nhóm nội bộ hoặc tài khoản kiểm thử được bật theo rule rõ ràng.

Nếu dùng percentage rollout, cần có bucketing ổn định dựa trên khóa phù hợp, chẳng hạn user ID hoặc tenant ID. Không dùng random mới cho mỗi request nếu mục tiêu là một user luôn ở cùng cohort trong một giai đoạn. Khi tăng tỷ lệ từ 10% lên 25%, cần hiểu những user nào sẽ được thêm vào và việc đổi cohort có ảnh hưởng đến dữ liệu hoặc trải nghiệm hay không.

Ví dụ ma trận targeting:

| Context | Rule | Kết quả mong đợi |
|---|---|---|
| User nội bộ | Allowlist nội bộ | ON |
| Tenant thử nghiệm | Tenant nằm trong allowlist | ON |
| User thuộc bucket rollout | Bucket dưới ngưỡng hiện tại | ON |
| User ngoài bucket | Bucket trên ngưỡng | OFF |
| Thiếu user ID | Không đánh giá được cohort | Dùng default đã định nghĩa |
| Tenant bị loại trừ | Explicit deny/exclusion | OFF dù thỏa rule rộng hơn |

Nếu có rule allow và deny đồng thời, cần định nghĩa precedence rõ ràng và test cả trường hợp xung đột. Không để thứ tự rule trong dashboard trở thành hành vi ngầm mà nhóm không hiểu.

## 7. Test chuyển trạng thái ON/OFF

Một flag thường được thay đổi trong lúc ứng dụng đang chạy. Vì vậy, cần kiểm tra chuyển trạng thái chứ không chỉ trạng thái tĩnh.

Các chuyển đổi chính:

- OFF → ON: tính năng mới bắt đầu được sử dụng.
- ON → OFF: hệ thống trở lại hành vi cũ hoặc chế độ an toàn.
- OFF → ON → OFF: xác minh có thể bật, tắt và bật lại mà không để lại trạng thái lỗi.
- Provider available → unavailable → available: kiểm tra cache và fallback.

Đặc biệt, cần kiểm tra dữ liệu được tạo trong thời gian ON. Khi tắt cờ, ứng dụng có thể vẫn phải đọc dữ liệu đó, hoặc phải tiếp tục tương thích với record/event đã được tạo. Tắt flag không tự động hoàn tác database migration, message đã phát, email đã gửi hoặc giao dịch đã hoàn tất.

Nếu một hành động không thể đảo ngược, ví dụ gửi thanh toán hoặc gửi thông báo, test phải xác định rõ điều gì xảy ra khi flag thay đổi giữa chừng. Không nên giả định việc đổi flag có thể hủy side effect đã thực hiện.

## 8. Kiểm tra dữ liệu và database migration

Feature flag thường được dùng để tách thời điểm deploy code khỏi thời điểm bật tính năng. Nhưng database schema và dữ liệu có thể khiến việc tắt flag không còn đơn giản.

Ví dụ, tính năng mới thêm cột pricing_model:

1. Deploy schema mở rộng nhưng vẫn tương thích code cũ.
2. Deploy code có thể đọc cả schema cũ và mới; flag mặc định OFF.
3. Bật flag cho cohort thử nghiệm và ghi dữ liệu theo schema mới.
4. Xác minh dữ liệu, khả năng đọc và các consumer khác.
5. Chỉ xóa cột hoặc đường tương thích cũ sau khi tính năng ổn định và hết rollback window.

Test cần bao gồm:

- Code cũ chạy trên schema sau khi mở rộng.
- Code mới chạy khi flag OFF.
- Code mới chạy khi flag ON.
- Record được tạo bởi nhánh ON vẫn có thể được đọc khi flag OFF nếu yêu cầu nghiệp vụ cần.
- Rollback ứng dụng không làm migration không tương thích gây lỗi.

Đây là lý do nên dùng chiến lược expand-and-contract. Thay đổi schema phá hủy hoặc đổi nghĩa dữ liệu trước khi hết thời gian rollback có thể khiến việc tắt flag không phục hồi được hệ thống.

## 9. Đặt test ở nhiều tầng

Không cần kiểm tra mọi tổ hợp ở end-to-end. Hãy phân bổ test theo chi phí và loại bằng chứng:

| Tầng | Nội dung kiểm tra | Mục tiêu |
|---|---|---|
| Unit test | Flag ON/OFF, default, fallback, rule selection | Kiểm tra logic rẽ nhánh nhanh và xác định |
| Component test | Service mới/cũ, side effect, transaction | Xác minh hợp đồng của từng thành phần |
| Integration test | Database, message broker, API, cache | Kiểm tra tương tác giữa các hệ thống |
| Contract test | Schema/API/event ở hai trạng thái | Giữ tương thích với consumer/provider |
| End-to-end test | Luồng người dùng khi ON và OFF | Xác nhận hành vi xuyên hệ thống |
| Staging/canary | Targeting, rollout, metric và chuyển trạng thái | Kiểm tra cấu hình gần thực tế trước mở rộng |

Unit test nên bao phủ cả hai nhánh vì chúng nhanh và dễ điều khiển trạng thái cờ. Integration test tập trung vào khác biệt có side effect. E2E nên chọn một số luồng nghiệp vụ đại diện để xác nhận toàn hệ thống, tránh nhân đôi mọi trường hợp ở mọi tầng.

## 10. Làm cho test feature flag có tính xác định

Test không nên phụ thuộc vào trạng thái flag thật đang được quản trị trên production. Nếu CI đọc trực tiếp remote flag service, cùng một commit có thể cho kết quả khác nhau tùy thời điểm hoặc cấu hình người vận hành vừa sửa.

Nên:

- Inject interface hoặc provider cho phép test đặt trạng thái flag tường minh.
- Dùng fake/stub deterministic trong unit test.
- Dùng fixture cấu hình đã version hóa trong integration test.
- Ghi lại snapshot hoặc version của flag configuration khi chạy staging test.
- Không dùng production secret hoặc production flag environment trong CI validation.
- Kiểm tra riêng khả năng kết nối remote provider ở một job phù hợp, không để mọi unit test phụ thuộc mạng.
- Reset trạng thái flag giữa các test để tránh rò rỉ state.

Ví dụ interface Java:

```java
public interface FeatureFlags {
    boolean isEnabled(
        String key,
        EvaluationContext context,
        boolean defaultValue
    );
}
```

Test có thể dùng implementation cố định:

```java
final class FixedFeatureFlags implements FeatureFlags {
    private final Map<String, Boolean> values;

    FixedFeatureFlags(Map<String, Boolean> values) {
        this.values = Map.copyOf(values);
    }

    @Override
    public boolean isEnabled(
        String key,
        EvaluationContext context,
        boolean defaultValue
    ) {
        return values.getOrDefault(key, defaultValue);
    }
}
```

Với fake này, test có thể tạo hai instance riêng: một instance trả OFF và một instance trả ON. Không cần sửa trạng thái trong hệ thống flag từ xa để kiểm tra nhánh logic.

## 11. Ví dụ unit test cho cả hai nhánh

Ví dụ với JUnit 5 và một dịch vụ tính giá:

```java
class PricingServiceTest {
    @Test
    void usesLegacyPricingWhenFlagIsOff() {
        FeatureFlags flags = new FixedFeatureFlags(
            Map.of("new-pricing", false)
        );
        PricingService service = new PricingService(
            flags,
            new LegacyPricing(),
            new NewPricing()
        );

        Price result = service.calculate(sampleOrder(), testContext());

        assertEquals(expectedLegacyPrice(), result);
    }

    @Test
    void usesNewPricingWhenFlagIsOn() {
        FeatureFlags flags = new FixedFeatureFlags(
            Map.of("new-pricing", true)
        );
        PricingService service = new PricingService(
            flags,
            new LegacyPricing(),
            new NewPricing()
        );

        Price result = service.calculate(sampleOrder(), testContext());

        assertEquals(expectedNewPrice(), result);
    }
}
```

Tên constructor và fixture là ví dụ, cần điều chỉnh theo code của dự án. Hai test nên kiểm tra kết quả nghiệp vụ cụ thể. Nếu hai thuật toán có thể cho cùng một kết quả ở input đơn giản, hãy chọn input làm lộ rõ khác biệt hoặc kiểm tra thêm side effect/interaction để chứng minh đúng nhánh được dùng.

Ngoài kết quả, có thể kiểm tra nhánh OFF không gọi NewPricing, còn nhánh ON không gọi LegacyPricing nếu hợp đồng yêu cầu chỉ một implementation được thực thi. Tránh kiểm tra quá nhiều chi tiết nội bộ không thuộc hợp đồng vì sẽ khiến test dễ vỡ khi refactor.

## 12. Quản lý nhiều feature flag và tránh bùng nổ tổ hợp

Với n feature flag Boolean độc lập, số tổ hợp lý thuyết là 2^n. Sáu cờ đã tạo ra 64 tổ hợp; mười cờ tạo ra 1.024 tổ hợp. Không phải mọi tổ hợp đều có ý nghĩa hoặc cần chạy E2E.

Để chọn phạm vi:

1. Xác định flag nào có tương tác trực tiếp về dữ liệu, API, permission hoặc side effect.
2. Test đầy đủ ON/OFF cho từng flag quan trọng ở unit/component level.
3. Test các cặp flag có dependency hoặc có thể xung đột.
4. Dùng pairwise/combinatorial testing cho các tổ hợp cấu hình lớn khi phù hợp.
5. Chọn một số kịch bản end-to-end đại diện theo rủi ro.
6. Kiểm tra các trạng thái không hợp lệ hoặc bị cấm theo policy.

Pairwise testing giúp mọi cặp giá trị được xuất hiện ít nhất một lần trong tập test, nhưng không chứng minh mọi tương tác ba hoặc nhiều cờ đều đúng. Với các tổ hợp có rủi ro cao, cần test tường minh.

Nên biểu diễn dependency giữa flag. Ví dụ new-checkout chỉ hợp lệ khi new-cart-api đã bật. Nếu cấu hình cho phép bật checkout nhưng API chưa sẵn sàng, test cần xác minh ứng dụng chặn cấu hình đó hoặc dùng fallback đã định nghĩa.

## 13. Kiểm tra coverage và bằng chứng trong CI

Pipeline nên chứng minh cả nhánh ON và OFF đã được thực thi trong bộ test bắt buộc. Branch coverage có thể giúp phát hiện một nhánh chưa được chạy, nhưng coverage không thay thế assertion về kết quả và side effect.

Một CI job tham khảo:

```yaml
jobs:
  feature_flag_tests:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout
        uses: actions/checkout@<FULL_COMMIT_SHA>
      - name: Run unit and component tests
        run: ./gradlew test componentTest
      - name: Publish test reports
        if: always()
        run: ./gradlew aggregateTestReports
```

Các action SHA và task componentTest, aggregateTestReports là placeholder cần thay bằng cấu hình thực tế của dự án. Report nên lưu commit SHA, test run, flag configuration fixture/version và kết quả. Nếu job report chạy sau khi test thất bại, trạng thái tổng hợp vẫn phải phản ánh test failure.

Với staging hoặc canary, lưu cohort/targeting configuration version, artifact digest, thời điểm đổi flag và metric trong khoảng quan sát. Không ghi dữ liệu cá nhân hoặc secret vào test report; chỉ lưu định danh cần thiết theo chính sách riêng tư.

## 14. Feature flag cần có vòng đời

Feature flag không nên tồn tại vĩnh viễn mà không có người chịu trách nhiệm. Một flag lâu ngày có thể tạo thêm nhánh logic, làm tăng số tổ hợp và khiến test suite phức tạp.

Khi tạo flag, ghi nhận:

- Tên/key và mô tả hành vi điều khiển.
- Loại flag và giá trị mặc định an toàn.
- Owner chịu trách nhiệm.
- Ngày tạo và ngày dự kiến xem xét/xóa.
- Các dependency hoặc flag liên quan.
- Nhóm người dùng/environment được phép bật.
- Test bắt buộc cho ON, OFF và fallback.

Sau khi rollout hoàn tất:

1. Xác nhận tính năng mới đã ổn định và không cần quay về nhánh cũ.
2. Xóa flag và nhánh code không còn cần thiết trong một thay đổi được review.
3. Xóa targeting rule, dashboard và override cũ.
4. Cập nhật test để chỉ giữ hành vi được hỗ trợ.
5. Kiểm tra database/schema sau khi hết rollback window trước khi dọn phần tương thích cũ.

Không xóa flag trước khi xác nhận mọi môi trường đã dùng cùng hành vi và không còn consumer cần nhánh cũ. Đặc biệt, kill switch hoặc operational toggle có thể cần được giữ lâu dài nếu nó là cơ chế an toàn vận hành.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ test flag ON | Hành vi cũ có thể bị hỏng khi OFF | Có test hồi quy cho OFF |
| Chỉ test flag OFF | Code mới chưa được xác minh | Test ON trước khi mở cohort |
| Dùng flag provider thật trong unit test | Kết quả phụ thuộc mạng và cấu hình ngoài | Inject fake/stub deterministic |
| Không test default và provider failure | Lỗi cấu hình có thể làm bật nhầm tính năng | Test missing/invalid/unavailable states |
| Chỉ kiểm tra response | Side effect ngoài ý muốn không bị phát hiện | Kiểm tra event, write, API call và transaction |
| Dùng random bucketing mỗi request | User liên tục đổi nhóm | Dùng bucketing ổn định theo identity |
| Bật cờ nhưng schema chưa tương thích | Lỗi dữ liệu hoặc rollback không an toàn | Dùng expand-and-contract và test cả hai nhánh |
| Tạo quá nhiều tổ hợp E2E | Pipeline chậm và khó bảo trì | Phân tầng test và chọn tổ hợp theo rủi ro |
| Giữ flag cũ vô thời hạn | Tăng nhánh logic và nợ kiểm thử | Có owner, expiry và quy trình cleanup |

## 16. Checklist kiểm tra feature flag ON/OFF

- [ ] Mỗi flag có mô tả, owner, loại, default và hành vi an toàn khi provider lỗi.
- [ ] Có unit/component test riêng cho nhánh ON và OFF.
- [ ] Nhánh OFF giữ hợp đồng cũ và không tạo side effect mới ngoài dự kiến.
- [ ] Nhánh ON đáp ứng acceptance criteria và kiểm tra lỗi dependency.
- [ ] Missing flag, invalid value, timeout và cached value được kiểm tra.
- [ ] Targeting, allowlist/denylist, percentage rollout và stable bucketing có test.
- [ ] Có test chuyển OFF → ON và ON → OFF, bao gồm dữ liệu/side effect đã phát sinh.
- [ ] Schema và migration tương thích với code cũ/mới trong rollback window.
- [ ] Test dùng fake/config fixture xác định, không phụ thuộc production flag service.
- [ ] Các tổ hợp flag được chọn theo dependency và rủi ro; không dựa duy nhất vào pairwise.
- [ ] CI lưu test report, commit, artifact và flag configuration version.
- [ ] Flag có vòng đời, owner và kế hoạch loại bỏ khi không còn cần thiết.

Kiểm tra cả hai trạng thái giúp feature flag trở thành cơ chế phát hành có thể kiểm soát. Khi nhánh OFF bảo vệ hành vi hiện tại, nhánh ON được kiểm chứng đầy đủ, fallback và targeting có test, nhóm có thể triển khai code trước rồi mở tính năng dần mà vẫn duy trì khả năng tắt hoặc phục hồi khi cần.
