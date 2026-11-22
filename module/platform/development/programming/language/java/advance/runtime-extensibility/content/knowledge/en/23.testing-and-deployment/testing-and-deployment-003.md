# Kiểm thử không có, có một, có nhiều và có provider cấu hình lỗi

## 1. Vì sao bốn tình huống này là tối thiểu?

Trong một hệ thống Java hỗ trợ plugin, cơ chế khám phá provider có thể đến từ \`ServiceLoader\`, registry, dependency injection hoặc \`ModuleLayer\`. Việc tìm được danh sách provider **không đồng nghĩa** rằng danh sách đó có đúng số lượng, tương thích API, được cấu hình hợp lệ hoặc an toàn để kích hoạt.

Tối thiểu, một plugin manager phải được kiểm thử với bốn trạng thái:

1. **Không có provider:** cơ chế khám phá trả về rỗng hoặc không có ứng viên đáp ứng yêu cầu.
2. **Có đúng một provider:** có thể chọn và gọi provider theo hợp đồng.
3. **Có nhiều provider:** áp dụng chính sách chọn một, gọi tất cả hoặc xây pipeline; không để thứ tự khám phá quyết định ngầm.
4. **Có provider cấu hình lỗi:** metadata, dependency, constructor, factory hoặc lifecycle không hợp lệ; host phải xử lý lỗi có kiểm soát.

Bốn nhóm này kiểm tra cả *discovery*, *validation*, *selection* và *activation*. Chúng giúp ngăn một số lỗi phổ biến: gọi \`iterator().next()\` khi rỗng, lựa chọn ngẫu nhiên giữa nhiều provider, khởi tạo một plugin hỏng làm sập toàn bộ host hoặc công bố một registry chứa provider chưa sẵn sàng.

## 2. Xác định hợp đồng trước khi viết test

Giả sử host có service:

\`\`\`java
public interface ExportProvider {
    String id();
    boolean supports(String format);
    String export(String payload);
}
\`\`\`

Host cần một **selection policy** cụ thể. Ví dụ trong bài này: với một định dạng yêu cầu, phải có **đúng một** provider hỗ trợ; không có thì báo thiếu; nhiều hơn một thì báo mơ hồ; provider khởi tạo lỗi phải bị từ chối, không âm thầm đưa vào registry.

Quy tắc này không phải bắt buộc cho mọi kiến trúc:

| Mục đích | Chính sách có thể phù hợp |
|---|---|
| Chọn một bộ xuất dữ liệu | Exactly-one provider hoặc priority tường minh |
| Gửi sự kiện cho logger, audit, metrics | All-providers/broadcast với aggregate result |
| Chạy bước validate → transform → persist | Pipeline có thứ tự và fail policy |
| Tìm handler đầu tiên chấp nhận request | Chain of Responsibility/fallback có điều kiện dừng |

**Trước khi test, phải viết rõ chính sách.** Nếu không, tình huống “nhiều provider” sẽ không có kết quả mong đợi xác định. Không nên lấy thứ tự \`ServiceLoader\` hay \`HashMap\` làm ưu tiên nghiệp vụ.

## 3. Ma trận kiểm thử trọng tâm

| Tình huống | Dữ liệu thiết lập | Kỳ vọng |
|---|---|---|
| Không có provider | Registry rỗng | Báo lỗi \`NO_PROVIDER\` hoặc degraded mode đã quy định |
| Một provider | Một implementation hợp lệ | Chọn đúng và gọi đúng một lần |
| Nhiều provider cùng hỗ trợ | Hai implementation cùng \`supports("csv")\` | Báo \`AMBIGUOUS_PROVIDER\` nếu áp dụng exactly-one |
| Nhiều provider khác khả năng | CSV provider và JSON provider | Chọn đúng provider theo format |
| Provider cấu hình lỗi | Thiếu ID, duplicate ID, sai API version | Từ chối trước khi công bố |
| Provider tạo instance lỗi | Factory/constructor ném exception | Ghi nguyên nhân; không publish instance hỏng |
| Provider thực thi lỗi | \`export\` ném exception | Phân loại runtime failure và giữ registry nhất quán |
| Plugin được thay thế | V1 hoạt động, V2 được chuẩn bị | Chỉ publish V2 sau validation/health check |
| Thử lại sau lỗi | Có side effect từ lần thử đầu | Không retry mù quáng gây lặp tác động |

Nhóm bốn trường hợp cốt lõi nên được mở rộng thành các ca âm như trùng ID, thứ tự không ổn định và rollback. Test không chỉ kiểm tra “có exception hay không”; còn phải kiểm tra **không có side effect không mong muốn**, registry không bị thay đổi một phần và log/diagnostic đủ rõ.

## 4. Tình huống không có provider

Khi discovery không tìm được provider:

\`\`\`text
Request(format=csv)
       |
       v
Discovery / Registry: []
       |
       v
NO_PROVIDER
\`\`\`

Có ít nhất ba cách xử lý hợp lệ tùy yêu cầu:

- **Bắt buộc phải có provider:** từ chối startup hoặc request bằng lỗi có mã ổn định.
- **Tính năng tùy chọn:** đánh dấu unavailable/degraded, không để tính năng không liên quan bị ảnh hưởng.
- **Fallback được phê duyệt:** chọn một implementation mặc định thực sự tương thích, không tự động “đoán” provider.

Kiểm thử nên xác nhận không có \`NoSuchElementException\`, \`NullPointerException\` hoặc message mơ hồ. Với \`ServiceLoader\`, \`findFirst()\` trả \`Optional\`; dùng \`orElseThrow\` với lỗi có ngữ nghĩa ứng dụng thay vì \`get()\` không kiểm tra.

**Không được giả định danh sách rỗng nghĩa là không có JAR:** JAR có thể tồn tại nhưng thiếu service registration, module chưa được resolve, factory không công bố service hoặc class loader không nhìn thấy provider. Unit test registry rỗng và integration test discovery thật giải quyết hai lớp lỗi khác nhau.

## 5. Tình huống đúng một provider

Với một provider hợp lệ, kiểm thử nên xác nhận:

1. Provider được discover/đăng ký.
2. Metadata và compatibility được kiểm tra trước activation.
3. \`supports\` áp dụng đúng loại yêu cầu.
4. Provider được gọi **một lần**, nhận đúng input và trả đúng output.
5. Lifecycle \`start\`/\`stop\` hoặc \`close\` được quản lý theo contract.
6. Instance được chọn có đúng ID, version và class loader dự kiến.

Đừng chỉ assert output nếu nhiều provider có thể tạo cùng output; cần xác minh provider **thực sự được gọi**. Với mocks/fakes có thể đếm số lời gọi; với integration test, dùng log, metrics hoặc một side effect kiểm soát được.

Một provider hợp lệ nhưng trả \`supports=false\` với request hiện tại phải được coi là **không có ứng viên phù hợp**, không phải mặc nhiên dùng nó vì registry chỉ có một phần tử.

## 6. Tình huống nhiều provider

Có nhiều provider không nhất thiết là lỗi. Câu hỏi là **chính sách nào đang được kiểm thử**.

### Exactly-one

Nếu hai provider cùng hỗ trợ \`csv\` nhưng host yêu cầu một nơi chịu trách nhiệm, nên phát hiện mơ hồ và từ chối thay vì chọn “phần tử đầu tiên”.

\`\`\`text
providers = [CsvA, CsvB]
request = csv
matches = [CsvA, CsvB]
=> AMBIGUOUS_PROVIDER
\`\`\`

### Fan-out

Nếu cả audit và metrics cần nhận một event, test phải xác nhận mỗi bên được gọi đúng một lần. Cần quy tắc rõ khi một handler thất bại: fail-fast hay best-effort; nếu bất đồng bộ, test thêm timeout, backpressure và idempotency.

### Pipeline

Nếu các bước tạo output nối tiếp, test phải kiểm tra thứ tự và việc output bước trước trở thành input bước sau. Một implementation duyệt \`Set\` không có order ổn định không phù hợp nếu thứ tự ảnh hưởng kết quả.

### Priority

Nếu host dùng priority, test cần cả trường hợp priority khác nhau và **bằng nhau**. Khi tie, phải có tie-breaker được công bố hoặc trả lỗi cấu hình. Test không nên dựa trên thứ tự discovery tình cờ.

## 7. Tình huống provider cấu hình lỗi

“Provider cấu hình lỗi” có thể xảy ra ở nhiều giai đoạn:

| Giai đoạn | Ví dụ lỗi | Kỳ vọng |
|---|---|---|
| Metadata | Thiếu \`Plugin-Id\`, ID không hợp lệ, sai schema | Reject artifact, không gọi mã provider |
| Version | API host không thỏa requirement | Reject trước activation |
| Dependency | Module/service dependency thiếu | Không publish; báo dependency cụ thể |
| Factory | Constructor ném exception | Phân loại startup failure; cleanup phần đã mở |
| Registration | Hai provider dùng cùng ID | Reject theo duplicate policy |
| Health check | Khởi tạo xong nhưng kiểm tra không đạt | Giữ registry cũ; đóng instance mới |
| Runtime | Method provider ném exception | Báo lỗi invocation, không mặc nhiên xóa toàn bộ registry |

Không nên đưa tất cả về một \`catch (Exception) { return emptyList(); }\`: như vậy cấu hình sai bị ngụy trang thành “không có provider”, làm chẩn đoán cực khó.

Trong \`ServiceLoader\`, quá trình duyệt có thể khởi tạo provider và ném \`ServiceConfigurationError\` khi declaration hoặc provider lỗi. Lỗi linkage cũng có thể xảy ra; cần ghi nhận nguyên nhân. Chính sách bắt lỗi tại ranh giới plugin phải tránh che giấu lỗi JVM nghiêm trọng hoặc tiếp tục sau khi trạng thái host không còn đáng tin.

## 8. Ví dụ Java 17+ độc lập: kiểm thử cả bốn tình huống

Ví dụ dưới đây dùng một registry trong bộ nhớ để cô lập **logic lựa chọn và validation** khỏi cơ chế discovery. Chạy được trên JDK 17+ mà không cần JUnit hay dependency ngoài.

Lưu thành **\`ProviderScenarios.java\`**:

\`\`\`java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ProviderScenarios {
    interface Provider {
        String id();
        boolean supports(String format);
        String run(String input);
    }

    record SimpleProvider(String id, String format) implements Provider {
        @Override
        public boolean supports(String requested) {
            return format.equals(requested);
        }

        @Override
        public String run(String input) {
            return id + ":" + input;
        }
    }

    static final class SelectionException extends RuntimeException {
        SelectionException(String code) {
            super(code);
        }
    }

    static List<Provider> validate(List<Provider> discovered) {
        List<Provider> ready = new ArrayList<>();
        for (Provider provider : discovered) {
            if (provider == null || provider.id() == null ||
                    provider.id().isBlank()) {
                throw new SelectionException("INVALID_PROVIDER");
            }
            if (ready.stream().anyMatch(
                    existing -> existing.id().equals(provider.id()))) {
                throw new SelectionException("DUPLICATE_PROVIDER_ID");
            }
            ready.add(provider);
        }
        return List.copyOf(ready);
    }

    static Provider selectOne(List<Provider> providers, String format) {
        Objects.requireNonNull(format, "format");
        List<Provider> matches = providers.stream()
                .filter(p -> p.supports(format))
                .toList();
        if (matches.isEmpty()) {
            throw new SelectionException("NO_PROVIDER");
        }
        if (matches.size() != 1) {
            throw new SelectionException("AMBIGUOUS_PROVIDER");
        }
        return matches.get(0);
    }

    static void expectFailure(String expected, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected);
        } catch (SelectionException e) {
            if (!expected.equals(e.getMessage())) {
                throw new AssertionError(
                        "Expected " + expected + ", got " + e.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        // 1. Không có provider.
        expectFailure("NO_PROVIDER",
                () -> selectOne(validate(List.of()), "csv"));
        System.out.println("empty: PASS");

        // 2. Đúng một provider.
        List<Provider> single = validate(List.of(
                new SimpleProvider("csv-main", "csv")));
        String result = selectOne(single, "csv").run("report");
        if (!"csv-main:report".equals(result)) {
            throw new AssertionError(result);
        }
        System.out.println("single: PASS");

        // 3. Nhiều provider cùng hỗ trợ một format.
        List<Provider> multiple = validate(List.of(
                new SimpleProvider("csv-a", "csv"),
                new SimpleProvider("csv-b", "csv")));
        expectFailure("AMBIGUOUS_PROVIDER",
                () -> selectOne(multiple, "csv"));
        System.out.println("multiple: PASS");

        // 4. Provider cấu hình lỗi: ID trống.
        expectFailure("INVALID_PROVIDER",
                () -> validate(List.of(
                        new SimpleProvider(" ", "csv"))));
        System.out.println("invalid: PASS");
    }
}
\`\`\`

Biên dịch và chạy:

\`\`\`bash
javac ProviderScenarios.java
java ProviderScenarios
\`\`\`

Stdout chính xác:

\`\`\`text
empty: PASS
single: PASS
multiple: PASS
invalid: PASS
\`\`\`

Giải thích:

- Mỗi \`expectFailure\` xác minh **mã lỗi dự kiến**; nếu action không lỗi hoặc lỗi sai, test thất bại bằng \`AssertionError\`.
- Registry validate trước khi chọn, và \`List.copyOf\` tạo danh sách không thể sửa qua API.
- Một provider thành công trả output để xác minh đường gọi.
- Trường hợp nhiều provider áp dụng policy **exactly-one**, nên lỗi mơ hồ là hành vi mong đợi.
- Trường hợp cấu hình lỗi chỉ kiểm tra ID trống; để test đủ lifecycle cần thêm fake factory và health check.

**Giới hạn của ví dụ:** không có \`ServiceLoader\`, không có class loader động và không tự mô phỏng lỗi factory. Đây là unit test cấp selection/validation, không thay thế integration test plugin packaging.

## 9. Integration test với ServiceLoader: kiểm tra đúng artifact

Sau khi logic selection ổn định, phải kiểm thử cơ chế khám phá thật:

\`\`\`java
// Đoạn tích hợp: Provider là service interface đã công bố;
// classpath/module path phải được test fixture chuẩn bị.
ServiceLoader<Provider> loader = ServiceLoader.load(Provider.class);
List<Provider> discovered = new ArrayList<>();
for (Provider provider : loader) {
    discovered.add(provider);
}
List<Provider> ready = validate(discovered);
\`\`\`

Đây không phải chương trình độc lập; cần interface \`Provider\` và provider registration thật.

**Classpath provider:** JAR khai báo file:

\`\`\`text
META-INF/services/com.example.spi.Provider
\`\`\`

với nội dung là tên đầy đủ của implementation. **JPMS provider:** explicit module khai báo:

\`\`\`java
provides com.example.spi.Provider with com.example.plugin.CsvProvider;
\`\`\`

Module host tiêu thụ service cần khai báo \`uses com.example.spi.Provider\` theo thiết kế JPMS; API service phải được chia sẻ đúng class identity giữa host và plugin.

Các fixture integration nên tách biệt để tránh tình trạng test này làm ảnh hưởng test khác:

1. Fixture không có service registration.
2. Fixture một provider hợp lệ.
3. Fixture hai provider hợp lệ, bao gồm trùng format và khác format.
4. Fixture broken registration, missing dependency hoặc constructor/factory lỗi.

Việc tạo **class loader hoặc ModuleLayer mới cho từng fixture** giúp kiểm thử cô lập và tránh cache/discovery ngoài dự kiến. Tuy nhiên, fixture cũng phải mô phỏng cơ chế loader thực tế của host để phát hiện vấn đề parent delegation và API duplicate.

## 10. Kiểm tra lỗi thực khi duyệt ServiceLoader

\`ServiceLoader\` có thể phát sinh \`ServiceConfigurationError\` trong các tình huống như provider declaration không hợp lệ, class provider không tồn tại hoặc không thể tạo instance. Nếu code:

\`\`\`java
ServiceLoader.load(Provider.class).stream().toList()
\`\`\`

thì việc thu thập danh sách provider metadata không giống việc gọi mọi \`Provider.get()\`; tùy API và cơ chế, lỗi có thể xuất hiện ở thời điểm tạo \`Provider\` wrapper, đọc \`type()\` hoặc khởi tạo instance. Hãy thử **đúng đường code mà production sử dụng**, bao gồm \`Provider.get()\`, constructor và lifecycle start.

Một nguyên tắc kiểm thử:

\`\`\`text
Artifact chưa được duyệt
        |
  manifest/module descriptor validation
        |
  trusted source/version/dependency checks
        |
  discovery/provider creation
        |
  initialization + health check
        |
    publish registry
\`\`\`

Nếu gói lỗi, registry hoạt động phải giữ snapshot cũ. Không được publish từng provider dở dang rồi phát hiện một provider khác lỗi giữa chừng.

Với lỗi dự đoán được ở một plugin tùy chọn, host có thể quarantine plugin đó và cho các plugin khác hoạt động theo policy; với service bắt buộc, startup có thể phải thất bại. Test cần phản ánh policy, không mặc định mọi lỗi đều phải shutdown toàn bộ ứng dụng.

## 11. Test lifecycle và công bố registry nguyên tử

Nếu host hỗ trợ hot reload, test bốn tình huống còn liên quan đến state transition.

Ví dụ:

\`\`\`text
Registry V1 (đang ACTIVE)
        |
Prepare Registry V2
   |-- validate metadata
   |-- construct providers
   |-- start + health check
   |
   +-- lỗi --> close V2 partial, V1 vẫn ACTIVE
   |
   +-- PASS --> atomic publish V2
                   |
                  drain V1
                   |
                  close V1
\`\`\`

Những assertion quan trọng:

- Trước publish, reader chỉ thấy V1; sau publish, reader mới thấy V2.
- Không có snapshot chứa nửa V1 nửa V2 nếu ứng dụng yêu cầu atomic registry version.
- Provider lỗi lúc start không được xuất hiện trong active registry.
- Nếu reader cũ đang gọi V1, writer không đóng V1 quá sớm.
- Resource của provider khởi tạo một phần phải được dọn ngay cả khi startup thất bại.

\`AtomicReference<ImmutableRegistry>\` hữu ích cho atomic publication; còn an toàn của \`stop/close\` cần lease/drain hoặc đồng bộ lifecycle khác. Unit test với fake providers có thể đếm \`start\`, \`run\`, \`stop\` và chèn lỗi có kiểm soát.

## 12. Test lỗi và khả năng quan sát

Kiểm tra không chỉ API response mà còn thông tin vận hành:

| Kiểm thử | Điều cần quan sát |
|---|---|
| Không provider | Error code, service/format yêu cầu, môi trường discovery |
| Một provider | Provider ID/version được chọn và invocation count |
| Nhiều provider | Danh sách ID trùng điều kiện, chính sách resolution |
| Config sai | Plugin ID, trường lỗi, validation reason |
| Factory lỗi | Error class, root cause, resource cleanup |
| Startup lỗi | Registry không đổi, không còn resource tạm |
| Runtime lỗi | Request failure isolation, không retry side effect mù quáng |

Không log secret, credential hoặc payload nhạy cảm. Nếu một plugin không đáng tin, constructor hoặc static initializer của nó có thể có side effect; integration test nên chạy trong môi trường cách ly, với dữ liệu giả và quyền hạn tối thiểu.

## 13. Các lỗi phổ biến khi thiết kế test

- Chỉ test một provider thành công rồi coi hệ plugin đã ổn.
- Không test danh sách rỗng hoặc thiếu service registration.
- Dùng \`findFirst()\` mà không kiểm tra trường hợp nhiều provider trùng khả năng.
- Test dựa trên thứ tự \`ServiceLoader\` mà không có ordering policy.
- Coi “không có provider” và “provider cấu hình hỏng” là cùng một lỗi.
- Gọi constructor thật của plugin bên thứ ba trong unit test không có sandbox.
- Test một \`HashMap\` đơn giản rồi giả định JPMS/module path sẽ hoạt động.
- Chỉ assert exception type mà không kiểm tra registry và resource sau thất bại.
- Coi việc tạo provider thành công là đã kiểm tra toàn bộ lifecycle.
- Cho nhiều test dùng chung loader/registry và rò state giữa các fixture.
- Không có kiểm thử race khi thay snapshot plugin trong lúc request đang chạy.

## 14. Checklist trước triển khai

Trước khi phát hành hệ thống plugin:

- Có test **zero / one / many / invalid** với kết quả tường minh?
- Có chính sách chọn provider khi nhiều ứng viên, bao gồm duplicate/tie?
- Có test provider supports sai format và provider ID trùng?
- Có integration test service metadata/classloader/module layer của artifact cuối cùng?
- Có kiểm tra version/API/capability trước startup?
- Có test constructor/start/health failure và cleanup?
- Có kiểm tra atomic registry publish, drain và rollback?
- Có kiểm tra runtime failure, timeout và idempotency?
- Có log/metrics đủ để phân biệt discovery, selection, configuration và invocation failures?
- Có giới hạn quyền và tài nguyên khi test plugin thiếu tin cậy?

**Ghi nhớ:** bốn ca **không có, một, nhiều và cấu hình lỗi** là nền tảng để chứng minh plugin manager không chỉ hoạt động trong “happy path”. Test tốt phải xác minh **hành vi lựa chọn, lỗi rõ ràng, trạng thái registry nhất quán và lifecycle an toàn** trên cả unit test lẫn artifact thực tế.
