# Định nghĩa hành vi khi không có provider hoặc nhiều provider cùng phù hợp

Trong kiến trúc mở rộng Java, hệ thống thường tìm các **provider** (những implementation của một interface hoặc Service Provider Interface, SPI) rồi chọn provider đáp ứng yêu cầu hiện tại. Vấn đề quan trọng không chỉ là *tìm được provider*, mà là **quyết định có thể dự đoán được** khi không tìm thấy ứng viên, khi tìm thấy nhiều ứng viên, hoặc khi provider được chọn không khởi tạo hay thực thi thành công.

Một chính sách lựa chọn tốt cần trả lời trước bốn câu hỏi:

1. **Không có provider nào được đăng ký:** ứng dụng thất bại, bỏ qua tính năng, hay dùng bản mặc định?
2. **Có provider nhưng không provider nào phù hợp yêu cầu:** có được dùng fallback không, và fallback có thật sự hỗ trợ yêu cầu đó?
3. **Nhiều provider đều phù hợp:** ưu tiên cấu hình tường minh, điểm ưu tiên, lựa chọn duy nhất, hay phối hợp nhiều provider?
4. **Provider hợp lệ nhưng lỗi khi nạp hoặc chạy:** có dừng, thử provider khác, hay báo lỗi nghiệp vụ? Đây là lỗi khác với “không có provider”.

Không nên để kết quả phụ thuộc vào việc JAR nào xuất hiện trước trên classpath hoặc provider nào vô tình được duyệt đầu tiên.

## 1. Phân biệt phát hiện, phù hợp, lựa chọn và thực thi

Giả sử ứng dụng công bố interface `DocumentRenderer` để xuất tài liệu; các JAR cung cấp `PdfRenderer`, `HtmlRenderer` hoặc một provider dự phòng. Có bốn bước cần phân biệt:

```text
Danh sách JAR / module khả dụng
             |
             v
[1] DISCOVER: tìm và khởi tạo các provider
             |
             v
[2] FILTER: provider nào hỗ trợ yêu cầu?
             |
             v
[3] SELECT: đúng một provider, nhiều provider, hay fallback?
             |
             v
[4] EXECUTE: gọi provider đã chọn, xử lý lỗi và tài nguyên
```

- **Không tìm thấy provider:** registry hoặc tập được phát hiện là rỗng. Đây có thể là thiếu JAR, thiếu khai báo dịch vụ hoặc tính năng tùy chọn chưa được cài.
- **Không có provider phù hợp:** registry không rỗng nhưng mọi ứng viên đều từ chối yêu cầu dựa trên capability, format, tenant, version hoặc chính sách.
- **Mơ hồ (ambiguous):** ít nhất hai ứng viên cùng đạt tiêu chí cao nhất và chính sách yêu cầu chọn duy nhất.
- **Lỗi discovery:** descriptor dịch vụ sai, class không load được, constructor/provider method lỗi, dependency không tương thích. Đây **không phải** trường hợp không có provider hợp lệ.
- **Lỗi execution:** một provider đã được chọn nhưng thất bại khi xử lý. Không thể kết luận rằng provider khác sẽ cho kết quả tương đương.

Việc giữ riêng từng trạng thái tạo ra thông báo lỗi, metric và chính sách khôi phục chính xác.

## 2. Chính sách khi không có provider phù hợp

Không có chính sách mặc định đúng cho mọi hệ thống. Hãy dựa vào việc tính năng đó **bắt buộc hay tùy chọn**, và có một kết quả dự phòng **đúng nghĩa nghiệp vụ** hay không.

| Chính sách | Hành vi | Dùng khi | Rủi ro cần tránh |
|---|---|---|---|
| **Fail fast / fail closed** | Trả lỗi có mã rõ ràng; khi khởi động có thể từ chối khởi động | Chức năng thiết yếu, mã hóa, thanh toán, kiểm tra quyền | Không đổi thành “cho phép” hoặc kết quả giả để tiếp tục |
| **Explicit fallback** | Chỉ gọi provider dự phòng đã cấu hình và đã xác minh hỗ trợ request | Xuất text thay định dạng phong phú, chế độ cơ bản | Fallback làm sai định dạng, mất dữ liệu hay âm thầm hạ mức bảo vệ |
| **No-op có chủ đích** | Bỏ qua tác vụ và ghi nhận trạng thái | Telemetry/hook tùy chọn, chức năng phụ không ảnh hưởng tính đúng | Báo thành công dù tác vụ bắt buộc chưa chạy |
| **Unsupported / disabled** | Trả trạng thái tính năng không được hỗ trợ hoặc chưa bật | Capability chỉ cài cho một số môi trường/tenant | Người gọi hiểu nhầm là lỗi hạ tầng thoáng qua |
| **Chờ/tải provider ngoài** | Chỉ khi hệ thống thiết kế cơ chế provisioning có giới hạn thời gian | Nền tảng tải plugin theo yêu cầu | Tải mã tùy ý hoặc treo request vô thời hạn |

Ví dụ: không có plugin tạo ảnh xem trước thì có thể hiển thị “chưa có preview”; không có provider xác thực chữ ký số thì phải báo lỗi hoặc từ chối thao tác, tuyệt đối không coi là đã xác thực.

**Fallback cần điều kiện rõ ràng:**

- Chỉ dùng cho lỗi `NO_PROVIDERS` / `NO_MATCH` nếu nghiệp vụ cho phép. Không tự áp dụng cho `AMBIGUOUS`, `DISCOVERY_FAILED` hoặc `EXECUTION_FAILED`.
- Có identity/version cố định, được kiểm thử, cấu hình và giám sát như provider thông thường.
- Có kiểm tra `supports(request)` và hạn chế dữ liệu/format; không giả định provider “default” hỗ trợ mọi đầu vào.
- Là lựa chọn **cuối cùng**, không âm thầm che việc bản phát hành thiếu plugin bắt buộc.
- Tách đường thành công bình thường và thành công do fallback trong log, metric và phản hồi khi điều đó ảnh hưởng đến người dùng.

Phân biệt “registry rỗng” với “không match” giúp chẩn đoán đúng: trường hợp đầu thường do cài đặt hoặc discovery, trường hợp sau có thể do khả năng hỗ trợ hoặc request ngoài phạm vi.

## 3. Chính sách khi nhiều provider cùng phù hợp

Có nhiều provider phù hợp **không đồng nghĩa phải lấy provider đầu tiên**. Tùy mục đích, thiết kế một trong các hợp đồng dưới đây.

| Chính sách | Quy tắc | Ví dụ |
|---|---|---|
| **Require unique match** | Đúng một ứng viên mới hợp lệ; từ hai trở lên trả `AMBIGUOUS_PROVIDER` | Một codec chuyên biệt duy nhất cho format đã đăng ký |
| **Explicit provider ID** | Cấu hình/người gọi chọn ID đã được cho phép; yêu cầu ID ấy phải tồn tại và hỗ trợ request | Tenant A chọn `s3-v2`, tenant B chọn `azure-v1` |
| **Priority + reject tie** | Chọn priority cao nhất; nếu nhiều provider cùng priority cao nhất thì trả lỗi mơ hồ | Chọn implementation chuyên biệt hơn generic |
| **Specificity + priority** | So theo mức độ cụ thể của capability/tenant rồi mới so priority; hòa cuối cùng vẫn phải có chính sách | Provider cho `image/png` cụ thể hơn `image/*` |
| **Ordered chain** | Thử ứng viên theo thứ tự được cấu hình, với điều kiện tiến trình thử an toàn | Parser có khả năng trả “không nhận diện được” trước khi xử lý |
| **Composition / fan-out** | Chủ động gọi nhiều provider và gom kết quả theo giao thức rõ ràng | Gửi cùng event tới nhiều sink giám sát |

**Không nhầm “chain” với “composition”:** chain thường tìm một provider xử lý thành công; composition chủ ý sử dụng nhiều provider. Chỉ thực hiện cả hai khi extension contract cho phép. Với thao tác có side effect như trừ tiền hoặc gửi email, thử nhiều provider sau một lỗi mơ hồ có thể gây thực thi lặp.

### Thứ tự ưu tiên cần ổn định

Nếu dùng priority, nên công bố rõ:

1. **Điều kiện bắt buộc:** provider phải được bật, tương thích API, nằm trong danh sách được phép và hỗ trợ request.
2. **Lựa chọn tường minh** nếu có: ID được chỉ định phải tồn tại và hỗ trợ request; nếu sai, trả lỗi thay vì lặng lẽ chuyển sang provider khác.
3. **Xếp hạng:** ví dụ priority là số nguyên, **số lớn hơn được ưu tiên**; nếu có specificity, phải công bố thứ tự xét.
4. **Xử lý hòa:** báo `AMBIGUOUS_PROVIDER` hoặc có một quy tắc business đã được thống nhất. Sắp xếp ID chỉ để tạo báo lỗi ổn định **không tự biến hòa thành lựa chọn đúng**.
5. **Fallback:** chỉ xét khi **không còn ứng viên hợp lệ**, nếu chính sách cho phép.

Không nên dựa vào thứ tự duyệt của `ServiceLoader`, thứ tự classpath, tên file JAR hoặc thứ tự provider được tải về. Những yếu tố đó có thể thay đổi giữa môi trường triển khai.

## 4. Ví dụ Java 17 chạy được: không có provider, chọn theo priority và phát hiện mơ hồ

Ví dụ sau triển khai một selector **độc lập với cách tìm provider**. Trong thực tế, danh sách `registry` có thể được lấy từ `ServiceLoader`, module layer hoặc plugin registry do ứng dụng quản lý. Selector này áp dụng chính sách:

- Nếu registry rỗng: `NO_PROVIDERS`; nếu có provider nhưng không ứng viên nào hỗ trợ: `NO_MATCH`.
- Fallback chỉ được dùng khi không có ứng viên phù hợp, và chính fallback phải hỗ trợ request.
- Nếu có ứng viên: lấy priority cao nhất. Hai ứng viên cùng priority cao nhất gây `AMBIGUOUS`, không lấy tùy tiện một cái.
- ID provider phải có giá trị và không được trùng trong registry.

Lưu thành tệp **`ProviderSelectionDemo.java`**:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class ProviderSelectionDemo {

    record Request(String kind, String data) {}

    interface Provider {
        String id();
        int priority();
        boolean supports(Request request);
        String execute(Request request);
    }

    record SimpleProvider(String id, int priority, String kind, String prefix)
            implements Provider {

        @Override
        public boolean supports(Request request) {
            return kind.equals("*") || kind.equals(request.kind());
        }

        @Override
        public String execute(Request request) {
            return prefix + ":" + request.data();
        }
    }

    record Selection(Provider provider, boolean fallback) {}

    static Selection select(
            Request request, List<Provider> registry, Provider fallback) {

        Set<String> ids = new HashSet<>();
        for (Provider provider : registry) {
            if (provider == null || provider.id() == null
                    || provider.id().isBlank()
                    || !ids.add(provider.id())) {
                throw new IllegalArgumentException("INVALID_REGISTRY");
            }
        }

        List<Provider> matches = registry.stream()
                .filter(provider -> provider.supports(request))
                .toList();

        if (matches.isEmpty()) {
            if (fallback != null && fallback.supports(request)) {
                return new Selection(fallback, true);
            }
            String code = registry.isEmpty() ? "NO_PROVIDERS" : "NO_MATCH";
            throw new IllegalStateException(
                    code + " kind=" + request.kind());
        }

        int maxPriority = matches.stream()
                .mapToInt(Provider::priority)
                .max()
                .orElseThrow();

        List<Provider> best = matches.stream()
                .filter(provider -> provider.priority() == maxPriority)
                .sorted(Comparator.comparing(Provider::id))
                .toList();

        if (best.size() != 1) {
            List<String> names = best.stream().map(Provider::id).toList();
            throw new IllegalStateException(
                    "AMBIGUOUS kind=" + request.kind()
                    + " priority=" + maxPriority
                    + " providers=" + names);
        }

        return new Selection(best.get(0), false);
    }

    static void demo(
            String label, String kind,
            List<Provider> registry, Provider fallback) {

        Request request = new Request(kind, "hello");

        try {
            Selection selection = select(request, registry, fallback);
            String mode = selection.fallback() ? "FALLBACK" : "SELECTED";
            System.out.println(
                    label + ": " + mode + " " + selection.provider().id()
                    + " -> " + selection.provider().execute(request));
        } catch (IllegalStateException exception) {
            System.out.println(label + ": " + exception.getMessage());
        }
    }

    public static void main(String[] args) {
        Provider basic =
                new SimpleProvider("basic", 10, "text", "BASIC");
        Provider premium =
                new SimpleProvider("premium", 20, "text", "PREMIUM");
        Provider alternate =
                new SimpleProvider("alternate", 20, "text", "ALT");
        Provider plain =
                new SimpleProvider("plain", 0, "*", "PLAIN");

        demo("empty-registry", "text", List.of(), null);
        demo("no-match", "csv", List.of(basic, premium), null);
        demo("unique-best", "text", List.of(basic, premium), null);
        demo("priority-tie", "text", List.of(premium, alternate), null);
        demo("fallback", "csv", List.of(basic), plain);
    }
}
```

Chạy với **JDK 17+**:

```bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
```

Stdout chính xác:

```text
empty-registry: NO_PROVIDERS kind=text
no-match: NO_MATCH kind=csv
unique-best: SELECTED premium -> PREMIUM:hello
priority-tie: AMBIGUOUS kind=text priority=20 providers=[alternate, premium]
fallback: FALLBACK plain -> PLAIN:hello
```

**Giải thích kết quả:**

- `empty-registry`: không đăng ký provider nào và không có fallback; lỗi được nhận diện là `NO_PROVIDERS`.
- `no-match`: hai provider đã đăng ký đều chỉ xử lý `text`; yêu cầu `csv` không có ứng viên nên trả `NO_MATCH`.
- `unique-best`: `basic` và `premium` đều xử lý `text`, nhưng `premium` có priority 20 cao hơn 10, nên được chọn.
- `priority-tie`: `premium` và `alternate` cùng priority 20. Sắp xếp ID cho **thông báo lỗi ổn định**; selector vẫn từ chối kết quả mơ hồ.
- `fallback`: `basic` không hỗ trợ `csv`; fallback `plain` công bố `kind="*"` nên được chọn và kết quả được đánh dấu `FALLBACK`.

Đây là chương trình minh họa **quyết định lựa chọn**, chưa phải một plugin manager production. Trong ứng dụng thật, cần thêm validation ở lúc đăng ký, kiểm soát quyền/capability, bảo vệ `supports` khỏi lỗi, cấu hình policy theo use case, lifecycle provider và xử lý lỗi thực thi.

## 5. Kết nối selector với ServiceLoader và plugin registry

`java.util.ServiceLoader` giúp tìm các implementation của một SPI mà các JAR/module công bố. Nó **không tự quyết định** provider nào được chọn khi có nhiều ứng viên phù hợp. Vì vậy, các bước thường là:

1. Định nghĩa interface/SPI ổn định, chẳng hạn `DocumentRenderer` có `id()`, `supports(request)` và `render(request)`.
2. Provider công bố qua `META-INF/services/<fully-qualified-interface>` hoặc `provides ... with ...` trong `module-info.java`.
3. Lấy **snapshot** provider ở một ranh giới lifecycle rõ ràng; kiểm tra ID, API version, availability và dependency.
4. Gọi selector với snapshot và request. Chỉ sau khi chọn xong mới thực thi provider.
5. Ghi lại provider ID/version và lý do chọn; release tài nguyên khi thay thế snapshot.

Đoạn **minh họa tích hợp** (giả định `DocumentRenderer` là một SPI công khai đã được định nghĩa; đây không phải chương trình độc lập):

```java
ServiceLoader<DocumentRenderer> loader =
        ServiceLoader.load(DocumentRenderer.class);

List<DocumentRenderer> discovered = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();

// Chuyển các provider vào selector/registry của ứng dụng,
// sau khi xác thực ID, API version, capability và policy.
```

`ServiceLoader` có cơ chế tìm/nạp provider theo nhu cầu, có thể phát sinh `ServiceConfigurationError` nếu khai báo hoặc provider không hợp lệ. Đừng bắt lỗi này rồi giả vờ registry rỗng: như vậy sẽ che lỗi đóng gói/dependency. `ServiceLoader.reload()` xóa cache provider của instance đó cho lượt tìm sau; nó **không tự phát hiện JAR mới**, không thay đối tượng đang phục vụ request và không cho phép sửa bytecode của class đã load. Nếu ứng dụng chủ động nạp JAR động, còn phải quản lý class loader/module layer và phiên bản snapshot.

### Khi cấu hình chỉ định provider cụ thể

Nếu một tenant cấu hình `provider.id=pdf-pro`, logic chọn nên:

1. Tìm theo đúng ID trong danh sách đã được tin cậy và cho phép.
2. Không thấy: trả `CONFIGURED_PROVIDER_NOT_FOUND`, thay vì lấy plugin đầu tiên.
3. Thấy nhưng không hỗ trợ request: `CONFIGURED_PROVIDER_UNSUPPORTED`.
4. Thấy hai mục trùng ID: `INVALID_REGISTRY` ngay lúc đăng ký; không để cái sau ghi đè cái trước.
5. Chỉ khi **không có chỉ định tường minh** mới xét chọn tự động theo policy.

Cách này cho phép kiểm thử cấu hình một cách lặp lại và tránh tình trạng thay classpath làm kết quả thay đổi mà không ai biết.

## 6. Phân biệt fallback khi không match với failover khi provider chạy lỗi

Hai thuật ngữ này dễ bị dùng lẫn:

- **Fallback khi không match:** không có implementation thích hợp; một default đã được chấp thuận xử lý thay, trước khi bắt đầu hành động chính.
- **Failover khi chạy lỗi:** implementation đã được chọn và có thể đã tạo side effect; thử implementation khác sau lỗi cần một hợp đồng retry/failover riêng.

Ví dụ provider gửi thanh toán bị timeout. Thời gian chờ không chứng minh giao dịch chưa hoàn thành; tự động gọi một provider khác có thể thu tiền lần thứ hai. Muốn failover phải xem khả năng **idempotency**, transaction boundary, deduplication, correlation ID, trạng thái chưa rõ và cách đối soát.

Nên định nghĩa các lỗi tối thiểu:

| Mã lỗi | Giai đoạn | Cách xử lý điển hình |
|---|---|---|
| `NO_PROVIDERS` | Discovery/registry | Kiểm tra JAR/descriptor/config; fallback nếu được định nghĩa |
| `NO_MATCH` | Capability filtering | Báo unsupported; fallback nếu provider dự phòng hỗ trợ |
| `AMBIGUOUS_PROVIDER` | Selection | Yêu cầu ID cụ thể hoặc sửa priority/policy |
| `INVALID_REGISTRY` | Registration | Từ chối registry có ID trùng, thiếu ID hoặc API không tương thích |
| `DISCOVERY_FAILED` | Provider loading | Báo cấu hình/plugin hỏng, ngừng hoặc cô lập extension theo policy |
| `PROVIDER_CHECK_FAILED` | Predicate `supports` | Đánh dấu provider lỗi; không mặc nhiên xem như `false` |
| `EXECUTION_FAILED` | Invocation | Bảo toàn dấu vết, xử lý retry/failover theo tính an toàn nghiệp vụ |

Không nên gom mọi `RuntimeException` hoặc `ServiceConfigurationError` thành `NO_MATCH`. Bắt lỗi nên ở ranh giới có thể đưa ra quyết định khôi phục; đừng nuốt lỗi để cố duy trì “thành công” giả.

## 7. Quy định priority, specificity và quy tắc hòa

Trong registry lớn, chỉ một số nguyên priority có thể chưa đủ. Ví dụ:

- Provider A hỗ trợ `image/*`, priority 100.
- Provider B hỗ trợ riêng `image/png`, priority 50.
- Request cần `image/png`.

Nếu policy lấy priority lớn nhất trước, A thắng; nếu policy lấy **specificity** trước, B thắng. **Cả hai có thể hợp lệ**, nhưng cần định nghĩa và kiểm thử từ trước. Không được tự suy đoán rằng ưu tiên cao luôn đồng nghĩa provider phù hợp hơn.

Một policy rõ ràng có thể là thứ tự từ mạnh đến yếu:

```text
1. Explicit provider ID (nếu người gọi được phép chỉ định)
2. Eligibility: enabled + API compatible + supports(request)
3. Specificity score (exact format > format family > wildcard)
4. Priority (higher value wins)
5. Nếu vẫn hòa: AMBIGUOUS_PROVIDER
6. Fallback chỉ khi không có eligible candidate
```

Nếu cần deterministic winner ngay cả khi hòa, phải nêu **tie-breaker có ý nghĩa nghiệp vụ** (chẳng hạn provider được chỉ định trong config), đồng thời kiểm tra rằng cách chọn đó đáp ứng yêu cầu. Dùng thứ tự từ điển của ID có thể giúp tái lập kết quả, nhưng dễ che sai sót cấu hình khi hai provider đáng lẽ phải được đánh giá ngang nhau.

Với lựa chọn theo capability, cũng cần biết một provider quảng cáo nhiều format có thể không thực sự hỗ trợ mọi tùy chọn của từng format; `supports(request)` phải xem đủ những thuộc tính quyết định, không chỉ đuôi tên file.

## 8. Chính sách khi registry thay đổi lúc ứng dụng đang chạy

Provider có thể được bật/tắt, cập nhật JAR, đổi config, hoặc được phát hiện trong một lần reload. Khi đó không nên sửa registry dùng chung ngay giữa lúc đang chọn và thực thi:

- Tạo một **snapshot bất biến** chứa ID, version, capability, priority và trạng thái healthy đã được xác thực.
- Với một request, dùng cùng snapshot xuyên suốt thao tác lựa chọn; không lọc trên bản cũ rồi lấy implementation từ bản mới.
- Nếu cập nhật thành công, atomically công bố snapshot mới để request sau sử dụng; request đang chạy có thể hoàn thành trên snapshot cũ.
- Chỉ unload/close provider/class loader cũ sau khi hết tham chiếu hoặc theo chính sách lifecycle đã định; loader/class vẫn tồn tại khi còn tham chiếu giữ lại.
- Khi chính sách mới làm xuất hiện mơ hồ, từ chối công bố snapshot nếu có thể kiểm tra trước theo danh sách capability được biết; với điều kiện request động, xử lý `AMBIGUOUS_PROVIDER` ở runtime.
- Nếu provider được chọn không còn healthy, đừng âm thầm thay bằng provider khác giữa transaction; chọn lại tại ranh giới request an toàn.

Các bảo đảm này thuộc về plugin registry của ứng dụng; `ServiceLoader` chỉ là một cách phát hiện implementation và không cung cấp lifecycle/hot swap hoàn chỉnh.

## 9. Quan sát và kiểm thử chính sách lựa chọn

Để giải thích được “vì sao hệ thống chọn provider X”, nên ghi nhận:

- **Tại discovery:** số provider tìm được, ID và version, lỗi descriptor/dependency, kết quả validation.
- **Tại filter:** loại request/capability, số ứng viên hợp lệ, nguyên nhân bị loại (disabled, unsupported, version mismatch).
- **Tại select:** policy/version, ID được chọn, priority/specificity, danh sách ID hòa, có dùng fallback hay không.
- **Tại execution:** provider ID/version, duration, success/failure, retry/failover đã thực hiện.

Ví dụ log có cấu trúc (minh họa, không phải stdout của chương trình trên):

```text
event=provider_selected capability=render/text provider=premium policy=highest-priority fallback=false
event=provider_selection_failed capability=render/text code=AMBIGUOUS_PROVIDER candidates=[alternate,premium]
event=provider_fallback capability=render/csv provider=plain reason=NO_MATCH
```

Tránh ghi toàn bộ payload tài liệu, token, khóa bảo mật hoặc thông tin cá nhân chỉ để chẩn đoán chọn provider.

### Bộ tình huống kiểm thử tối thiểu

| Trường hợp | Kỳ vọng |
|---|---|
| Registry rỗng, capability bắt buộc | `NO_PROVIDERS`, không báo xử lý thành công |
| Có registry nhưng không match, fallback không bật | `NO_MATCH` hoặc unsupported |
| Không match, fallback hợp lệ | Chọn fallback, đánh dấu lý do và kết quả |
| Không match, fallback cũng không hỗ trợ | Từ chối; không cưỡng ép chạy fallback |
| Một provider match | Chọn provider đó |
| Nhiều provider match, priority khác nhau | Chọn đúng provider cao nhất |
| Hai provider cùng priority cao nhất | `AMBIGUOUS_PROVIDER` hoặc tie-breaker đã định nghĩa |
| Hai provider trùng ID | `INVALID_REGISTRY` trước khi lựa chọn |
| Config chỉ định ID không tồn tại | Lỗi cấu hình cụ thể; không lặng lẽ chọn khác |
| Descriptor/JAR không load được | `DISCOVERY_FAILED`; không chuyển thành no-match |
| `supports()` ném lỗi | `PROVIDER_CHECK_FAILED`; không tự coi là không hỗ trợ |
| Provider đã chạy rồi ném timeout | `EXECUTION_FAILED`; chỉ failover nếu bảo đảm nghiệp vụ |
| Registry đổi version trong lúc request chạy | Request dùng snapshot đã chọn; bản mới áp dụng ở ranh giới an toàn |

Các test unit cho selector thường dễ thực hiện bằng provider giả lập như ví dụ Java. Test integration cần thêm JAR/`META-INF/services` hoặc module layer thực, trường hợp dependency lỗi và reload để kiểm tra đường discovery.

## 10. Lỗi thiết kế thường gặp

1. **“Lấy phần tử đầu từ ServiceLoader là đủ.”** Sai trong bài toán nhiều provider: thứ tự phát hiện không phải chính sách lựa chọn có ý nghĩa.
2. **“Không có provider nghĩa là không cần xử lý.”** Sai nếu capability bắt buộc; phải phân biệt optional với required.
3. **“Không match thì luôn fallback.”** Sai nếu fallback không hỗ trợ đầu vào hoặc làm giảm bảo mật/tính đúng.
4. **“Hai provider cùng priority thì lấy provider có ID nhỏ nhất.”** Điều đó deterministic nhưng không nhất thiết đúng nghiệp vụ; policy cần được thống nhất rõ.
5. **“Nhiều provider là lỗi.”** Không phải lúc nào cũng vậy: hệ thống broadcast hoặc chain có thể chủ đích dùng nhiều provider; cần hợp đồng phối hợp.
6. **“Lỗi nạp plugin là không có plugin.”** Sai: descriptor sai, dependency thiếu hoặc lỗi constructor cần thông báo riêng.
7. **“Gặp timeout thì thử provider kế tiếp.”** Có nguy cơ thực thi trùng side effect; cần idempotency và trạng thái giao dịch.
8. **“Đã chọn được provider thì không cần biết version.”** Version/API compatibility ảnh hưởng khả năng chạy, rollback và chẩn đoán.
9. **“ServiceLoader.reload() làm hot-swap tức thì.”** Sai: phải xây lớp quản lý snapshot, class loader, instance và lifecycle.
10. **“Priority là cơ chế kiểm soát quyền.”** Sai: provider chỉ được xem xét sau khi đã kiểm tra allowlist, quyền tenant và độ tin cậy; priority chỉ xếp hạng ứng viên hợp lệ.

**Nguyên tắc cần nhớ:** *Không có ứng viên* là quyết định về **required/optional/fallback**; *nhiều ứng viên* là quyết định về **uniqueness/priority/specificity/composition**; *provider lỗi* là quyết định về **recovery và tính an toàn nghiệp vụ**. Mỗi trạng thái phải có hành vi, mã lỗi và bằng chứng quan sát riêng để ứng dụng Java mở rộng được mà vẫn dự đoán và kiểm thử được.