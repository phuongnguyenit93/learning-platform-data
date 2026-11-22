# Thiết kế định danh, khả năng hỗ trợ và thông tin phiên bản cho hợp đồng mở rộng trong Java

## 1. Vì sao hợp đồng mở rộng cần ba nhóm thông tin này?

Một ứng dụng Java có thể mở rộng bằng plugin, provider của `ServiceLoader`, adapter hoặc implementation do bên thứ ba cung cấp. Chỉ biết tên class triển khai là chưa đủ để host quyết định có nên tiếp nhận một extension hay không. Host cần trả lời ba câu hỏi độc lập:

1. **Định danh (identity):** Đây là extension nào, thuộc điểm mở rộng nào, có trùng với extension đã đăng ký hay không?
2. **Khả năng hỗ trợ (capabilities):** Extension thực sự cam kết thực hiện được những tác vụ hoặc biến thể nào của hợp đồng?
3. **Thông tin phiên bản (version information):** Extension được xây dựng cho phiên bản giao diện nào, yêu cầu môi trường nào và bản thân implementation đang ở bản phát hành nào?

Ví dụ một hệ thống tìm kiếm cho phép gắn nhiều provider. Hai provider có thể cùng hiện tên “Search”, cùng triển khai interface `SearchProvider`, nhưng có ID khác nhau; một provider chỉ tìm kiếm văn bản, provider kia còn hỗ trợ tìm theo tiền tố. Cả hai cũng có thể có phiên bản sản phẩm khác nhau nhưng cùng tương thích với API của host.

| Trục | Ví dụ | Dùng để quyết định | Không nên dùng thay thế |
| --- | --- | --- | --- |
| Định danh | `vn.demo.search.basic` | Phân biệt, đăng ký, tham chiếu, phát hiện trùng | Tên hiển thị, tên class hoặc đường dẫn JAR |
| Khả năng | `search.text`, `search.prefix` | Chọn provider phù hợp cho yêu cầu cụ thể | Phiên bản cao/thấp hoặc phỏng đoán từ tên |
| Phiên bản API | `2.1` | Kiểm tra hợp đồng giao tiếp với host | Phiên bản phát hành của plugin |
| Phiên bản implementation | `1.4.2` | Theo dõi release, sự cố, nâng cấp | Bằng chứng rằng plugin tương thích |
| Phiên bản metadata/môi trường | `schemaVersion=1`, `minJavaFeature=17` | Đọc descriptor và kiểm tra điều kiện chạy | Version API của điểm mở rộng |

Ba trục này **phải được mô hình hóa riêng**. Một plugin được phát hành bản `1.5.0` không đương nhiên hỗ trợ API `1.5`; một plugin công bố `search.vector` không đương nhiên có quyền truy cập dữ liệu hoặc đang sẵn sàng phục vụ tại thời điểm gọi.

## 2. Thiết kế định danh ổn định

### 2.1. Phân biệt các loại ID

- **Extension point ID:** định danh hợp đồng mà host mở ra, ví dụ `vn.demo.search.provider`. Nó trả lời “mở rộng cái gì?”.
- **Extension/provider ID:** định danh ổn định của một implementation, ví dụ `vn.demo.search.basic`. Nó trả lời “bên nào cung cấp cách thực hiện này?”.
- **Instance ID:** định danh của một lần cấu hình hoặc kích hoạt provider, ví dụ `tenant-a/search-primary`. Nhiều instance có thể dùng chung một provider ID nhưng cấu hình khác nhau.
- **Display name:** tên cho con người đọc, ví dụ “Basic Search”. Tên này có thể được dịch hoặc đổi để dễ hiểu và không nên dùng làm khóa kỹ thuật.

Một chính sách dễ vận hành là dùng ID dạng chuỗi có namespace, toàn chữ thường, ví dụ `vn.demo.search.basic`, `vn.demo.search.lucene`. Reverse-domain hoặc namespace của tổ chức giúp giảm va chạm; đây là **quy ước do hệ thống định nghĩa**, không phải định dạng ID mà Java tự bắt buộc. Công bố rõ bộ ký tự hợp lệ, cách chuẩn hóa, quy tắc so sánh và phạm vi duy nhất (toàn host hay trong từng extension point).

Các tính chất quan trọng:

1. **Ổn định qua các lần phát hành:** sửa code, thay package hoặc nâng `implementationVersion` không làm đổi provider ID. Nếu đổi ID, cần cơ chế ánh xạ/di trú cho cấu hình, cache và dữ liệu đã lưu.
2. **Duy nhất theo chính sách registry:** cùng một khóa đăng ký không được âm thầm ghi đè. Trùng ID phải được báo lỗi rõ ràng, kèm thông tin nguồn plugin.
3. **Không phụ thuộc tên hiển thị hoặc tên class:** refactor Java package hay đổi nhãn UI không làm hỏng tham chiếu.
4. **Không gắn version vào ID ổn định:** `vn.demo.search.basic.v2` thường tạo ra một thực thể mới ngoài ý muốn. Trường hợp thật sự là một provider khác thì mới dùng ID khác.
5. **Có chủ sở hữu namespace:** một tên `vn.example.*` tự khai báo chưa chứng minh nguồn phát hành đáng tin. Xác minh publisher/chữ ký hoặc chính sách cấp phát ID là vấn đề riêng với việc kiểm tra cú pháp.

Nếu hệ thống cần cùng lúc hai phiên bản implementation của một provider, hãy định nghĩa rõ khóa registry, chẳng hạn `(providerId, instanceId)` hoặc `(providerId, deploymentSlot)`. Không tự ý biến `providerId` thành chuỗi bao gồm version rồi phá vỡ tham chiếu đã lưu.

### 2.2. Ranh giới giữa ID và tên triển khai Java

`ServiceLoader` nhận diện service bằng kiểu interface/abstract class và tìm các provider được khai báo qua `META-INF/services` hoặc module descriptor `provides ... with ...`. Nó **không tự cung cấp** ID nghiệp vụ, bộ capability hay version của từng provider. Nếu host cần ba thông tin này, phải định nghĩa thêm descriptor/contract của chính mình và xác thực chúng.

Cũng không nên suy luận ID từ tên class, `Class.getName()`, tên module JPMS hay tên tệp JAR: các tên đó phục vụ build/deploy và có thể đổi độc lập với danh tính extension.

## 3. Mô hình hóa khả năng hỗ trợ (capabilities)

Một interface thường mô tả mức thao tác chung, nhưng implementation có thể hỗ trợ các tính năng tùy chọn khác nhau. Hãy định nghĩa **capability key** có ý nghĩa ổn định và được tài liệu hóa, ví dụ:

- `search.text`: tìm văn bản bằng truy vấn theo hợp đồng đã công bố.
- `search.prefix`: tìm theo tiền tố, với quy tắc khớp và chuẩn hóa rõ ràng.
- `search.vector`: truy vấn theo vector, với chiều dữ liệu và quy tắc đo khoảng cách do hợp đồng bổ sung quy định.

Đừng dùng những nhãn mơ hồ như `advanced` hoặc `fast` để quyết định tính tương thích; “nhanh” là thuộc tính hiệu năng phụ thuộc phép đo, không phải một thao tác được cam kết.

### 3.1. Những tập hợp cần phân biệt

- **Provided capabilities:** tập khả năng plugin *cung cấp*, ví dụ `{search.text, search.prefix}`.
- **Required plugin capabilities:** những khả năng mà host/tác vụ *bắt buộc provider có*, ví dụ `{search.text}`.
- **Required host capabilities:** những dịch vụ host mà plugin *cần* (nếu kiến trúc có chiều phụ thuộc này), ví dụ `{host.events.v1}`.
- **Enabled/available capabilities:** tập khả năng hiện được bật và có thể sử dụng sau khi xét cấu hình, giấy phép, tài nguyên, backend, trạng thái kết nối. Đây có thể là tập con của provided capabilities.

Định nghĩa kiểm tra tập hợp ở mức đơn giản:

```text
requiredPluginCapabilities ⊆ provider.providedCapabilities
provider.requiredHostCapabilities ⊆ host.providedCapabilities
```

Sau khi vượt kiểm tra tương thích tĩnh, nếu một capability có thể tạm ngừng vì điều kiện runtime, host vẫn cần kiểm tra **trạng thái khả dụng** trước lúc gọi. Capability công bố không đồng nghĩa với “dịch vụ luôn đang khỏe”.

### 3.2. Thiết kế hợp đồng cho capability tùy chọn

- Đặt tên có namespace, sử dụng cùng một định dạng ở tài liệu, descriptor và mã nguồn. Tài liệu của từng key phải nêu rõ input, output, hành vi khi không hỗ trợ, ràng buộc dữ liệu và side effect.
- Nêu rõ **khả năng bắt buộc** để implement extension point và **khả năng tùy chọn**. Nếu `search.text` là bắt buộc thì provider chỉ quảng cáo `search.vector` không hợp lệ cho tác vụ cần tìm văn bản.
- Khi thêm capability, giữ khả năng tương thích ngược nếu hợp đồng đã hứa điều đó. Nếu thay đổi ý nghĩa đáng kể, tạo key/contract mới hoặc nâng major API theo chính sách, thay vì âm thầm đổi hành vi của key cũ.
- Không âm thầm “giả lập” capability chưa có: trả lỗi `UNSUPPORTED_CAPABILITY` có cấu trúc, hoặc chọn provider khác theo một fallback được khai báo và chấp nhận trước.
- Capability **không phải quyền truy cập**. Plugin nói mình hỗ trợ ghi file không có nghĩa host phải cấp quyền ghi file; authorization/sandbox vẫn do host kiểm soát.

Registry nên kiểm tra capability tĩnh khi nhận plugin, và các điểm gọi nên yêu cầu capability cụ thể thay vì lựa chọn bằng chuỗi tên hoặc số version.

## 4. Phân tách các loại version

Giữ ít nhất những khái niệm sau ở các trường khác nhau:

| Trường | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `implementationVersion` | Phiên bản phát hành của plugin/adapter, ví dụ `1.4.2` | Quan sát triển khai, nhật ký, truy vết lỗi, rollout |
| `apiVersion` hoặc `apiRange` | Phiên bản hợp đồng API/SPI mà plugin được biên dịch và kiểm thử để sử dụng | So khớp với những hợp đồng host hỗ trợ |
| `schemaVersion` | Phiên bản cấu trúc descriptor/manifest | Chọn parser/validator metadata thích hợp |
| `minJavaFeature` | Java feature release tối thiểu, ví dụ `17` | Loại sớm artifact không chạy được trong runtime hiện tại |
| `minHostVersion` / khoảng host version (nếu cần) | Điều kiện phụ thuộc vào sản phẩm host | Kiểm tra khác biệt ngoài API/SPI |

**Đừng so sánh version như chuỗi từ điển:** `"2.10"` lớn hơn `"2.9"` theo số phiên bản, dù so sánh chuỗi thông thường có thể cho kết quả ngược. Hãy parse từng thành phần số hoặc dùng thư viện SemVer phù hợp. Nếu dùng Semantic Versioning, cần định nghĩa rõ ý nghĩa của major/minor/patch, pre-release, build metadata và khoảng tương thích; không áp đặt quy ước đó cho những trường không tuân SemVer.

Một chính sách minh họa cho `apiVersion=MAJOR.MINOR`:

- Major phải nằm trong danh sách major host công bố hỗ trợ. Ví dụ host chỉ hỗ trợ API major 2 thì provider đòi API major 3 bị từ chối.
- Trong **cùng major**, host hỗ trợ đến minor 2.2 thì plugin yêu cầu 2.1 có thể được chấp nhận, plugin yêu cầu 2.3 bị từ chối, **chỉ nếu** hợp đồng quy định minor mới không phá hành vi cũ và host triển khai đủ tính năng của các minor trước.
- Patch hoặc version triển khai không được dùng để thay thế kiểm thử tương thích. Một plugin `implementationVersion=7.0.0` vẫn có thể yêu cầu API 2.1.

Trong Java, thay đổi chữ ký method, xóa method, đổi kiểu, thay cấu trúc exception hoặc thêm abstract method vào interface có thể làm hỏng mã đã biên dịch/triển khai dù chỉ nâng minor. Thay đổi hành vi cũng có thể gây lỗi dù liên kết nhị phân còn hợp lệ. Vì vậy, “cùng major là tương thích” là **cam kết phải được duy trì bằng thiết kế và test**, không phải tính năng tự động của JVM. Đối với tính năng tùy chọn, có thể cân nhắc interface riêng hoặc default method có semantics rõ ràng, nhưng vẫn phải kiểm thử mã cũ.

`Package.getImplementationVersion()` có thể lấy metadata từ manifest của package khi được đóng gói phù hợp, còn `ModuleDescriptor.version()` có thể có thông tin phiên bản của module. Các giá trị đó là **tùy chọn**, không thay thế descriptor tương thích do host định nghĩa và không chứng minh plugin đáng tin.

## 5. Ví dụ descriptor có thể kiểm tra bằng máy

Một host có thể quy định manifest độc lập với Java class như sau (đây là **schema minh họa do ứng dụng định nghĩa**, không phải file mà `ServiceLoader` tự đọc):

```json
{
  "schemaVersion": 1,
  "extensionPointId": "vn.demo.search.provider",
  "id": "vn.demo.search.basic",
  "displayName": "Basic Search",
  "implementationVersion": "1.4.2",
  "apiVersion": "2.1",
  "minJavaFeature": 17,
  "providedCapabilities": [
    "search.text",
    "search.prefix"
  ],
  "requiredHostCapabilities": []
}
```

Khi đọc descriptor, host cần kiểm tra trường bắt buộc, định dạng ID, kiểu dữ liệu, giá trị version, tên capability, duplicate và khoảng version hợp lệ. Nếu metadata sai, báo lỗi cụ thể; không sửa ngầm hoặc biến giá trị không rõ thành “tương thích”. Có thể xây dựng registry theo trạng thái `DISCOVERED → VALIDATED → COMPATIBLE → ENABLED` để phân biệt nhìn thấy plugin, xác thực metadata, chấp nhận hợp đồng và thực sự kích hoạt.

Nếu descriptor nằm bên trong JAR, host nên kiểm tra những điều kiện có thể đọc từ metadata **trước khi cố tải và khởi tạo class plugin**. Chỉ kiểm tra `minJavaFeature` sau khi đã nạp bytecode là quá muộn khi JAR chứa class được biên dịch cho Java mới hơn, vì `UnsupportedClassVersionError` có thể xuất hiện trước bước kiểm tra. Metadata và nguồn phát hành phải được xác minh theo chính sách tin cậy của host.

## 6. Ví dụ Java 17+: đăng ký và kiểm tra tương thích

Ví dụ dưới đây mô phỏng phần **descriptor + điều kiện host**, không phải một trình nạp JAR hay triển khai `ServiceLoader` hoàn chỉnh. Chính sách được chọn: ID duy nhất trong registry; API phải cùng major và minor plugin không vượt minor host hỗ trợ; môi trường Java và capability bắt buộc phải đáp ứng.

Tạo tệp `ExtensionContractDemo.java`:

```java
import java.util.*;

public class ExtensionContractDemo {
    record ApiVersion(int major, int minor) {
        ApiVersion {
            if (major < 1 || minor < 0) {
                throw new IllegalArgumentException("Invalid API version");
            }
        }
        @Override public String toString() {
            return major + "." + minor;
        }
    }

    record ExtensionDescriptor(
            String extensionPointId,
            String id,
            String displayName,
            String implementationVersion,
            ApiVersion apiVersion,
            int minJavaFeature,
            Set<String> providedCapabilities) {
        ExtensionDescriptor {
            if (!validId(extensionPointId) || !validId(id)) {
                throw new IllegalArgumentException("Invalid extension ID");
            }
            Objects.requireNonNull(displayName);
            Objects.requireNonNull(implementationVersion);
            Objects.requireNonNull(apiVersion);
            Objects.requireNonNull(providedCapabilities);
            if (minJavaFeature < 1) {
                throw new IllegalArgumentException("Invalid Java version");
            }
            providedCapabilities = Set.copyOf(providedCapabilities);
        }
    }

    record HostPolicy(
            String extensionPointId,
            ApiVersion supportedApi,
            Set<String> requiredCapabilities) {
        HostPolicy {
            if (!validId(extensionPointId)) {
                throw new IllegalArgumentException("Invalid extension point");
            }
            Objects.requireNonNull(supportedApi);
            requiredCapabilities = Set.copyOf(requiredCapabilities);
        }
    }

    static boolean validId(String id) {
        return id != null
                && id.matches("[a-z][a-z0-9]*(\\.[a-z][a-z0-9-]*)+");
    }

    static void ensureUniqueIds(List<ExtensionDescriptor> plugins) {
        Set<String> ids = new HashSet<>();
        for (ExtensionDescriptor plugin : plugins) {
            if (!ids.add(plugin.id())) {
                throw new IllegalArgumentException(
                        "Duplicate plugin ID: " + plugin.id());
            }
        }
    }

    static String check(ExtensionDescriptor plugin, HostPolicy host) {
        if (!plugin.extensionPointId().equals(host.extensionPointId())) {
            return "SAI_EXTENSION_POINT";
        }
        if (plugin.apiVersion().major() != host.supportedApi().major()) {
            return "SAI_API_MAJOR";
        }
        if (plugin.apiVersion().minor() > host.supportedApi().minor()) {
            return "API_MINOR_QUA_MOI";
        }
        if (plugin.minJavaFeature() > Runtime.version().feature()) {
            return "JAVA_CHUA_DAP_UNG";
        }
        if (!plugin.providedCapabilities()
                .containsAll(host.requiredCapabilities())) {
            return "THIEU_CAPABILITY";
        }
        return "OK";
    }

    public static void main(String[] args) {
        HostPolicy host = new HostPolicy(
                "vn.demo.search.provider", new ApiVersion(2, 2),
                Set.of("search.text"));

        List<ExtensionDescriptor> plugins = List.of(
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.basic",
                        "Basic Search", "1.4.2", new ApiVersion(2, 1), 17,
                        Set.of("search.text", "search.prefix")),
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.future",
                        "Future Search", "2.0.0", new ApiVersion(2, 3), 17,
                        Set.of("search.text")),
                new ExtensionDescriptor(
                        "vn.demo.search.provider", "vn.demo.search.vector",
                        "Vector Search", "1.1.0", new ApiVersion(2, 1), 17,
                        Set.of("search.vector")));

        ensureUniqueIds(plugins);
        for (ExtensionDescriptor plugin : plugins) {
            System.out.println(plugin.id() + " => " + check(plugin, host));
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên:

```bash
javac --release 17 ExtensionContractDemo.java
java ExtensionContractDemo
```

Kết quả:

```text
vn.demo.search.basic => OK
vn.demo.search.future => API_MINOR_QUA_MOI
vn.demo.search.vector => THIEU_CAPABILITY
```

Giải thích:

- `basic` có API 2.1 tương thích với chính sách API 2.2, yêu cầu Java 17 và cung cấp `search.text` nên được chấp nhận.
- `future` cung cấp đúng capability nhưng cần API 2.3, cao hơn mức host 2.2; không được dùng `implementationVersion=2.0.0` để bỏ qua chặn này.
- `vector` có API phù hợp nhưng không cung cấp `search.text`; host phải từ chối tác vụ đòi capability đó.

`Set.copyOf` chụp một bản tập hợp bất biến để tránh bên gọi sửa danh sách capability sau khi descriptor được tạo; `ensureUniqueIds` từ chối đụng độ ID thay vì để provider sau ghi đè provider trước. Thứ tự in ra ổn định do `List.of` giữ thứ tự khai báo; code không dựa vào thứ tự duyệt của `Set`.

Ví dụ chỉ trình bày **một chiều capability** (host yêu cầu plugin cung cấp). Nếu plugin cũng đòi dịch vụ từ host, phải thêm `requiredHostCapabilities` vào `ExtensionDescriptor` và kiểm tra chiều ngược lại. Hệ thống thực tế còn cần parse/validate schema, kiểm tra nguồn tin cậy, chính sách kích hoạt, trạng thái khả dụng runtime và test tương thích; không nên coi hàm `check` nhỏ này là toàn bộ bộ máy quản lý plugin.

## 7. Quy trình tiếp nhận extension an toàn, có thể quan sát

1. **Discover metadata:** tìm descriptor do extension công bố, biết rõ nguồn cung cấp nhưng chưa khởi tạo plugin.
2. **Validate:** kiểm tra schema, ID/namespace, kiểu trường, version và capability key; phát hiện duplicate. Bảo toàn nguyên nhân từ chối.
3. **Check compatibility:** so sánh extension point, API/range, Java runtime, các yêu cầu capability hai chiều và ràng buộc host đã công bố.
4. **Authorize and enable:** áp chính sách tin cậy và quyền, rồi mới khởi tạo provider; sau đó kiểm tra readiness/availability nếu capability phụ thuộc trạng thái chạy.
5. **Publish registry:** cung cấp bản ghi gồm ID, phiên bản, capability, trạng thái và lý do từ chối để chọn provider, logging, metrics, vận hành và hỗ trợ nâng cấp.

Một kết quả registry hữu ích có thể lưu `id`, `extensionPointId`, `implementationVersion`, `apiVersion`, `declaredCapabilities`, `availableCapabilities`, `status` và `reasonCode`. Với dữ liệu vận hành, tránh dùng `displayName` làm khóa truy vấn vì tên có thể thay đổi; dùng ID ổn định và ghi version riêng để phân biệt deployment.

Ở lớp xử lý request, chọn extension dựa trên **điểm mở rộng + capability yêu cầu + trạng thái khả dụng**; nếu nhiều provider phù hợp, dùng chính sách ưu tiên được cấu hình rõ. Nếu không có provider, phản hồi “không có implementation tương thích” với lý do có thể chẩn đoán, thay vì im lặng gọi một provider gần giống.

## 8. Những lỗi thiết kế thường gặp và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Lấy tên class/JAR làm ID | Refactor, shade hoặc đổi đóng gói làm mất cấu hình cũ | Đặt ID ổn định trong descriptor |
| Gắn số version vào ID | Mỗi lần cập nhật tạo khóa mới, khó migrate | Version là trường riêng; chỉ đổi ID khi thật sự đổi danh tính |
| Chấp nhận ID trùng theo thứ tự tải | Kết quả phụ thuộc thứ tự classpath/discovery | Từ chối trùng hoặc áp chính sách nhiều instance công khai |
| Dùng `implementationVersion` để kiểm tra API | Plugin mới vẫn có thể dùng hợp đồng cũ hoặc không tương thích | So sánh trường API/range độc lập |
| So version dạng chuỗi | Nhầm thứ tự `2.10` và `2.9` | Parse numeric/SemVer có quy tắc |
| Suy ra capability từ việc implement interface | Gọi tính năng không được hỗ trợ | Khai báo và kiểm tra capability ở điểm dùng |
| Đánh đồng capability với quyền hoặc trạng thái sẵn sàng | Gọi thất bại, vượt chính sách truy cập | Phân biệt provided, enabled/available và authorization |
| Tin metadata hoặc SemVer mà không kiểm thử | Lỗi liên kết nhị phân hoặc thay đổi hành vi | Bộ test hợp đồng/API trên nhiều version đã tuyên bố hỗ trợ |
| Nạp class trước khi kiểm tra yêu cầu Java | Có thể gặp `UnsupportedClassVersionError` quá sớm | Đọc descriptor và kiểm tra yêu cầu môi trường trước khi load |
| Âm thầm fallback khi thiếu tính năng | Kết quả không đúng semantics kỳ vọng | Lỗi rõ ràng hoặc fallback được người gọi đồng ý |

## 9. Checklist thiết kế hợp đồng

Một hợp đồng mở rộng đủ rõ cần trả lời được:

- Extension point và provider có ID ổn định, duy nhất, có chủ sở hữu namespace và quy tắc di trú khi đổi ID không?
- Capability key có semantics, điều kiện kích hoạt, danh sách bắt buộc/tùy chọn và cách báo unsupported nhất quán không?
- API version, implementation version, metadata schema version và điều kiện Java/host có độc lập và so sánh được bằng quy tắc rõ ràng không?
- Host có thể từ chối trước khi khởi tạo các plugin không tương thích, và có lưu lý do từ chối để xử lý sự cố không?
- Có test cho các trường hợp trùng ID, thiếu capability, API major/minor khác nhau, Java runtime không đủ, đổi version và nâng cấp plugin cũ không?

**Nguyên tắc cốt lõi:** ID giải quyết *extension nào*, capability giải quyết *extension làm được gì*, còn thông tin version giải quyết *hợp đồng và môi trường nào có thể làm việc cùng nhau*. Tách ba câu hỏi này giúp registry chọn đúng provider, nâng cấp có kiểm soát và chẩn đoán lỗi tương thích một cách nhất quán.