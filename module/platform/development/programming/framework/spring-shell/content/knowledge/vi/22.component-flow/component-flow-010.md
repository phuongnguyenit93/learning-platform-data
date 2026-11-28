# Kiểm thử các nhánh, hủy thao tác và giá trị mặc định

`ComponentFlow` trong Spring Shell 3.x ghép nhiều component nhập liệu thành một luồng tương tác. Khi flow có nhánh rẽ, xác nhận và giá trị mặc định, chỉ kiểm tra wizard hiển thị được là chưa đủ. Cần xác minh đúng component được chạy, kết quả được lưu, thao tác bị từ chối không tạo side effect và các giá trị mặc định không khiến người dùng vô tình xác nhận một hành động quan trọng.

Bài học sử dụng API `ComponentFlow` của Spring Shell 3.3.x. Trọng tâm gồm `next(...)`, `defaultValue(...)`, `resultValue(...)`, `ResultMode`, `ComponentFlowResult`, cùng bộ kiểm thử `@ShellTest` và `ShellTestClient`.

## 1. Cấu trúc một ComponentFlow

Một flow được xây dựng bằng `ComponentFlow.Builder`. Mỗi component có một ID duy nhất; builder thêm các component theo thứ tự mặc định. Có thể thay đổi luồng đi bằng hàm `next(...)`.

Các component thường dùng:

| Builder method | Loại input | Giá trị trả về |
|---|---|---|
| `withStringInput(id)` | Nhập văn bản | `String` |
| `withPathInput(id)` | Nhập đường dẫn | `String` |
| `withConfirmationInput(id)` | Xác nhận có/không | `Boolean` |
| `withSingleItemSelector(id)` | Chọn một mục | Một mục được chọn |
| `withMultiItemSelector(id)` | Chọn nhiều mục | Danh sách mục được chọn |

Ví dụ đơn giản:

```java
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;

@Component
public class SetupWizard {

    private final ComponentFlow.Builder componentFlowBuilder;

    public SetupWizard(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    public ComponentFlow.ComponentFlowResult run() {
        ComponentFlow flow = componentFlowBuilder.clone()
            .reset()
            .withStringInput("projectName")
                .name("Tên project")
                .defaultValue("demo")
                .and()
            .withConfirmationInput("create")
                .name("Tạo project?")
                .defaultValue(false)
                .and()
            .build();

        return flow.run();
    }
}
```

`clone().reset()` tạo một cấu hình builder mới từ builder được inject và xóa các component đã cấu hình trước đó. Cách này giúp mỗi lần chạy wizard bắt đầu từ cùng một định nghĩa, tránh tích lũy component nếu builder được dùng lại.

`build()` tạo `ComponentFlow`; `run()` thực thi flow và trả về `ComponentFlowResult`.

## 2. Thứ tự mặc định và điều hướng bằng next

Nếu không khai báo `next(...)`, các component chạy theo thứ tự được thêm vào builder.

Khi cần rẽ nhánh, `next(...)` nhận context của component vừa hoàn thành và trả về ID của component tiếp theo. ID này phải trùng với ID được truyền vào `withStringInput`, `withConfirmationInput` hoặc builder tương ứng.

Ví dụ:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, String> modes = new LinkedHashMap<>();
modes.put("Cơ bản", "basic");
modes.put("Nâng cao", "advanced");

ComponentFlow flow = componentFlowBuilder.clone()
    .reset()
    .withSingleItemSelector("mode")
        .name("Chọn cách cấu hình")
        .selectItems(modes)
        .next(ctx -> ctx.getResultItem().get().getItem())
        .and()
    .withStringInput("basic")
        .name("Tên project")
        .defaultValue("demo")
        .and()
    .withStringInput("advanced")
        .name("Tên project")
        .defaultValue("demo")
        .and()
    .build();
```

Trong ví dụ, selector trả về ID `basic` hoặc `advanced`, tương ứng với component có ID đó. Component không được chọn sẽ bị bỏ qua.

Quy tắc quan trọng của `next(...)`:

- Trả về ID hợp lệ: flow chuyển tới component có ID đó.
- Trả về `null`: flow dừng tại component hiện tại.
- Trả về ID không tồn tại: flow cũng dừng.

Dùng `null` để biểu diễn điểm dừng có chủ đích. Không nên trả một ID giả chỉ để ép flow dừng vì cách đó làm ý định điều hướng khó đọc.

## 3. Tách quyết định rẽ nhánh thành hàm thuần

Khi nhánh flow phụ thuộc vào một giá trị Boolean hoặc lựa chọn, hãy tách quyết định thành hàm nhỏ. Hàm này không đọc terminal, không gọi service và không thay đổi dữ liệu.

Ví dụ quyết định sau bước xác nhận:

```java
static String nextAfterConfirmation(Boolean approved) {
    return Boolean.TRUE.equals(approved) ? "releaseVersion" : null;
}
```

Dùng trong builder:

```java
.withConfirmationInput("confirm")
    .name("Xác nhận triển khai?")
    .defaultValue(false)
    .next(ctx -> nextAfterConfirmation(ctx.getResultValue()))
    .and()
.withStringInput("releaseVersion")
    .name("Phiên bản phát hành")
    .defaultValue("latest")
    .and()
```

Hàm dùng `Boolean.TRUE.equals(...)` để xử lý an toàn cả trường hợp giá trị là `null`. Chỉ giá trị `true` mới đi tiếp; `false` hoặc `null` đều dừng flow.

Việc tách hàm giúp kiểm thử nhánh mà không cần tạo terminal hoặc mô phỏng phím bấm.

## 4. Dùng xác nhận để hủy thao tác an toàn

Giả sử wizard thu thập môi trường và phiên bản trước khi triển khai. Người dùng phải xác nhận trước khi gọi service thực hiện thao tác.

```java
import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Service;

@Service
public class ReleaseWizard {

    private final ComponentFlow.Builder componentFlowBuilder;
    private final ReleaseService releaseService;

    public ReleaseWizard(
            ComponentFlow.Builder componentFlowBuilder,
            ReleaseService releaseService) {
        this.componentFlowBuilder = componentFlowBuilder;
        this.releaseService = releaseService;
    }

    public String run() {
        ComponentFlow flow = componentFlowBuilder.clone()
            .reset()
            .withStringInput("environment")
                .name("Môi trường")
                .defaultValue("staging")
                .and()
            .withConfirmationInput("confirm")
                .name("Xác nhận triển khai?")
                .defaultValue(false)
                .next(ctx -> nextAfterConfirmation(ctx.getResultValue()))
                .and()
            .withStringInput("releaseVersion")
                .name("Phiên bản")
                .defaultValue("latest")
                .and()
            .build();

        ComponentFlow.ComponentFlowResult result = flow.run();
        ComponentContext<?> values = result.getContext();

        Boolean approved = values.get("confirm", Boolean.class);
        if (!Boolean.TRUE.equals(approved)) {
            return "Đã hủy thao tác triển khai.";
        }

        String environment = values.get("environment", String.class);
        String version = values.get("releaseVersion", String.class);

        releaseService.deploy(environment, version);
        return "Đã triển khai " + version + " lên " + environment;
    }

    static String nextAfterConfirmation(Boolean approved) {
        return Boolean.TRUE.equals(approved) ? "releaseVersion" : null;
    }
}
```

Khi người dùng chọn `No`, `nextAfterConfirmation` trả về `null`, nên component `releaseVersion` không chạy. Sau khi `flow.run()` kết thúc, code đọc kết quả `confirm`; nếu giá trị không phải `true`, phương thức trả về ngay và không gọi `releaseService.deploy(...)`.

Đây là cách biểu diễn hủy thao tác ở cấp nghiệp vụ:

1. Người dùng từ chối xác nhận.
2. Flow dừng trước bước nhập phiên bản.
3. Kết quả `confirm=false` được đọc từ context.
4. Ứng dụng trả thông báo hủy.
5. Service thực hiện thao tác không được gọi.

`ComponentFlowResult` cung cấp `getContext()` để lấy context cuối của flow. Các input mặc định lưu kết quả vào context theo ID của component; `storeResult` mặc định là `true`. Nếu đặt `storeResult(false)`, component sẽ không tự lưu kết quả vào context, vì vậy không thể đọc giá trị đó theo cách trên.

### 4.1. Dừng flow không tự hoàn tác side effect

`next(null)` chỉ dừng các component tiếp theo. Nó không rollback những thao tác đã thực hiện trước đó.

Vì vậy, không nên gửi email, ghi dữ liệu, tạo tài nguyên hoặc triển khai thật trong `preHandler`, `postHandler` hay ngay trong hàm quyết định `next(...)` nếu các bước xác nhận vẫn còn ở phía sau.

Nên để các component thu thập và xác nhận dữ liệu. Chỉ gọi service thực hiện nghiệp vụ sau khi `flow.run()` kết thúc và ứng dụng xác minh kết quả xác nhận là `true`.

`ComponentFlowResult` có `getContext()`; API này không cung cấp một cờ `isCancelled()` riêng. Nếu ứng dụng cần phân biệt hủy, hãy lưu một lựa chọn xác nhận hoặc trạng thái nghiệp vụ rõ ràng trong flow context.

Việc nhấn Ctrl+C hoặc đóng terminal là một tình huống ngắt ở tầng terminal. Không nên tự coi nó là kết quả xác nhận `false`; hãy kiểm tra và xử lý hành vi interruption riêng theo cách ứng dụng khởi chạy shell.

## 5. Giá trị mặc định với defaultValue

`defaultValue(...)` đặt giá trị mặc định cho component input.

Ví dụ với chuỗi:

```java
.withStringInput("environment")
    .name("Môi trường")
    .defaultValue("staging")
    .and()
```

Nếu người dùng chấp nhận giá trị mặc định mà không thay đổi input, kết quả được lưu là `staging`.

Với xác nhận:

```java
.withConfirmationInput("confirm")
    .name("Xác nhận xóa dữ liệu?")
    .defaultValue(false)
    .and()
```

Giá trị mặc định `false` yêu cầu người dùng chủ động chọn đồng ý nếu muốn tiếp tục. Đây là lựa chọn an toàn cho thao tác xóa, ghi đè, phát hành hoặc thay đổi môi trường.

| Input | Giá trị mặc định gợi ý | Lý do |
|---|---|---|
| Môi trường phát triển | `dev` | Giá trị thường dùng khi chạy thử |
| Định dạng báo cáo | `json` | Hợp đồng output rõ ràng |
| Tên project mới | `demo` | Giá trị ví dụ dễ nhận biết |
| Xác nhận xóa | `false` | Không thực hiện khi người dùng chỉ nhấn Enter |
| Xác nhận ghi đè | `false` | Tránh ghi đè ngoài ý muốn |
| Xác nhận triển khai production | `false` | Yêu cầu đồng ý tường minh |

Giá trị mặc định nên phản ánh lựa chọn an toàn và phổ biến. Không nên dùng `true` làm mặc định cho thao tác có tác động lớn chỉ để giảm số lần người dùng nhập.

## 6. Phân biệt defaultValue, resultValue và ResultMode

Ba API này có vai trò liên quan nhưng khác nhau:

| API | Vai trò |
|---|---|
| `defaultValue(value)` | Đặt giá trị mặc định cho input |
| `resultValue(value)` | Cung cấp sẵn giá trị kết quả cho component |
| `resultMode(mode)` | Quyết định cách component xử lý giá trị `resultValue` |

`ResultMode` có hai giá trị:

- `VERIFY`: đưa `resultValue` vào component để người dùng kiểm tra. Thông thường giá trị được đặt làm mặc định, người dùng có thể tiếp tục hoặc thay đổi.
- `ACCEPT`: tự chấp nhận `resultValue`, bỏ qua bước chạy component và lưu giá trị làm kết quả.

Ví dụ yêu cầu người dùng xác minh môi trường mặc định:

```java
import org.springframework.shell.component.flow.ResultMode;

.withStringInput("environment")
    .name("Môi trường triển khai")
    .resultValue("staging")
    .resultMode(ResultMode.VERIFY)
    .and()
```

Ví dụ tự chấp nhận môi trường do hệ thống đã xác định:

```java
.withStringInput("environment")
    .name("Môi trường triển khai")
    .resultValue("staging")
    .resultMode(ResultMode.ACCEPT)
    .and()
```

Với `ACCEPT`, component được bỏ qua và giá trị `staging` được đưa vào kết quả. Với `VERIFY`, component vẫn chạy để người dùng kiểm tra giá trị đã được điền sẵn.

Không nên dùng `ACCEPT` cho bước xác nhận thao tác phá hủy nếu mục tiêu là yêu cầu người dùng đồng ý. Nếu cần người dùng xem lại, hãy dùng component xác nhận với mặc định `false` và kiểm tra kết quả trước khi thực hiện nghiệp vụ.

## 7. Đọc và kiểm tra kết quả của flow

`ComponentFlow.run()` trả về `ComponentFlow.ComponentFlowResult`. Kết quả cung cấp `getContext()` để truy xuất các giá trị được lưu theo ID component.

Ví dụ:

```java
ComponentFlow.ComponentFlowResult result = flow.run();
ComponentContext<?> context = result.getContext();

String environment = context.get("environment", String.class);
Boolean approved = context.get("confirm", Boolean.class);

if (!Boolean.TRUE.equals(approved)) {
    // Dừng nghiệp vụ vì người dùng không xác nhận.
    return;
}

// Chỉ sử dụng các giá trị đã được xác nhận.
releaseService.deploy(environment);
```

Có thể đọc giá trị theo kiểu mong muốn bằng `get(key, type)`. Cách này giúp tránh ép kiểu thủ công và làm rõ kiểu dữ liệu mà ứng dụng mong đợi.

Một số lưu ý:

- ID trong `get(...)` phải giống ID truyền cho builder.
- Kết quả chỉ được tự lưu nếu `storeResult` được bật; mặc định là `true`.
- Nếu một nhánh bị bỏ qua, không giả định component ở nhánh đó đã tạo ra giá trị.
- Luôn kiểm tra giá trị có thể `null` trước khi dùng.
- Không thực hiện nghiệp vụ chỉ vì flow đã kết thúc; phải kiểm tra trạng thái xác nhận và dữ liệu bắt buộc.

## 8. Kiểm thử hàm điều hướng bằng unit test

Vì hàm `nextAfterConfirmation` không phụ thuộc terminal hay Spring context, có thể kiểm thử trực tiếp bằng JUnit.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;

class ReleaseWizardTests {

    @Test
    void approvedMovesToVersionInput() {
        assertEquals(
            "releaseVersion",
            ReleaseWizard.nextAfterConfirmation(true)
        );
    }

    @Test
    void declinedStopsFlow() {
        assertNull(
            ReleaseWizard.nextAfterConfirmation(false)
        );
    }

    @Test
    void missingConfirmationAlsoStopsFlow() {
        assertNull(
            ReleaseWizard.nextAfterConfirmation(null)
        );
    }
}
```

Ba trường hợp cần có:

1. `true`: đi tiếp tới component nhập phiên bản.
2. `false`: dừng flow.
3. `null`: dừng flow an toàn.

Nếu flow có nhiều nhánh hơn, hãy tách mỗi quyết định thành hàm nhỏ và kiểm thử toàn bộ giá trị đầu vào có thể xảy ra. Không cần dựng terminal để kiểm tra một hàm điều hướng thuần.

## 9. Kiểm thử flow tương tác bằng ShellTestClient

Spring Shell 3.3 cung cấp `@ShellTest` và `ShellTestClient` để mô phỏng phiên terminal.

Ví dụ kiểm thử một flow:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ContextConfiguration;
import java.time.Duration;

import static org.awaitility.Awaitility.await;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.ArgumentMatchers.anyString;

@ShellTest
@ContextConfiguration(classes = ReleaseWizardApplication.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReleaseWizardInteractiveTests {

    @Autowired
    private ShellTestClient client;

    @MockBean
    private ReleaseService releaseService;

    @Test
    void defaultNoCancelsRelease() {
        ShellTestClient.InteractiveShellSession session =
            client.interactive().run();

        session.write(
            session.writeSequence()
                .command("release wizard")
                .build()
        );

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                .containsText("Môi trường")
        );

        // Chấp nhận giá trị mặc định "staging".
        session.write(
            session.writeSequence()
                .carriageReturn()
                .build()
        );

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                .containsText("Xác nhận triển khai?")
        );

        // Chấp nhận giá trị xác nhận mặc định false.
        session.write(
            session.writeSequence()
                .carriageReturn()
                .build()
        );

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() ->
            ShellAssertions.assertThat(session.screen())
                .containsText("Đã hủy thao tác triển khai.")
        );

        verify(releaseService, never())
            .deploy(anyString(), anyString());
    }
}
```

Ví dụ giả định `releaseService` được cung cấp dưới dạng mock trong test context và command `release wizard` gọi `ReleaseWizard.run()`.

`ShellTestClient` cung cấp phiên interactive và phương thức ghi input. `ShellWriteSequence` có thể tạo chuỗi phím bằng `text(...)`, `carriageReturn()` hoặc `command(...)`. `ShellAssertions` kiểm tra nội dung đang hiển thị trên `ShellScreen`.

Việc tương tác terminal có thể bất đồng bộ. Với test chạy không đồng bộ, hãy đợi prompt xuất hiện trước khi gửi phím tiếp theo và dùng timeout hữu hạn thay vì đọc màn hình ngay lập tức sau lệnh ghi.

### 9.1. Những trường hợp cần kiểm thử tích hợp

| Trường hợp | Input mô phỏng | Kết quả cần xác minh |
|---|---|---|
| Dùng mặc định môi trường | Nhấn Enter ở input môi trường | Context chứa `staging` |
| Từ chối xác nhận | Nhấn Enter khi default là `false` | Flow dừng, service không được gọi |
| Đồng ý xác nhận | Chọn `true` | Component nhập phiên bản xuất hiện |
| Nhánh nâng cao | Chọn `advanced` | Chỉ component `advanced` được chạy |
| Giá trị mặc định được xác minh | Dùng `ResultMode.VERIFY` | Component hiển thị giá trị điền sẵn |
| Giá trị tự chấp nhận | Dùng `ResultMode.ACCEPT` | Component bị bỏ qua và giá trị được lưu |
| Thiếu dữ liệu | Không có kết quả bắt buộc | Không gọi service với giá trị `null` |

Nên kiểm tra cả output lẫn side effect. Một thông báo “Đã hủy” không đủ chứng minh thao tác đã bị chặn; hãy xác minh service không được gọi hoặc repository không bị thay đổi.

## 10. Kiểm thử từng nhánh của selector

Với flow có nhiều lựa chọn, mỗi lựa chọn cần được kiểm tra riêng.

Ví dụ selector điều hướng tới `basic` hoặc `advanced`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, String> modes = new LinkedHashMap<>();
modes.put("Cơ bản", "basic");
modes.put("Nâng cao", "advanced");

ComponentFlow flow = componentFlowBuilder.clone()
    .reset()
    .withSingleItemSelector("mode")
        .name("Chế độ cấu hình")
        .selectItems(modes)
        .next(ctx -> ctx.getResultItem().get().getItem())
        .and()
    .withStringInput("basic")
        .name("Tên project")
        .defaultValue("demo")
        .and()
    .withStringInput("advanced")
        .name("Tên project")
        .defaultValue("demo")
        .and()
    .build();
```

Có thể tách phép ánh xạ lựa chọn thành hàm thuần nếu cần kiểm thử riêng. Với kiểm thử tương tác, mô phỏng từng lựa chọn trên `ShellTestClient`, sau đó xác minh prompt của component được chọn xuất hiện và prompt của nhánh còn lại không xuất hiện.

Không chỉ kiểm tra nhánh được chọn. Hãy xác minh nhánh còn lại thực sự bị bỏ qua, đặc biệt khi các nhánh có thể dẫn tới thao tác ghi dữ liệu khác nhau.

## 11. Các lỗi thường gặp khi kiểm thử ComponentFlow

**Trả sai ID trong `next(...)`.** ID không khớp với ID component sẽ khiến flow dừng. Đặt tên ID ngắn, rõ nghĩa và dùng hằng số nếu nhiều nơi cùng tham chiếu.

**Coi `next(null)` là rollback.** Nó chỉ dừng component tiếp theo. Mọi side effect đã thực hiện trước đó vẫn tồn tại. Chỉ gọi service sau khi xác nhận thành công.

**Đặt `defaultValue(true)` cho xác nhận nguy hiểm.** Người dùng có thể chấp nhận mặc định mà không đọc kỹ. Dùng `false` cho xóa, ghi đè hoặc triển khai.

**Nhầm `defaultValue` với `ResultMode.ACCEPT`.** `defaultValue` đặt giá trị mặc định cho input; `ACCEPT` bỏ qua component và tự chấp nhận `resultValue`.

**Tắt `storeResult` nhưng vẫn đọc context.** Nếu `storeResult(false)`, kết quả không tự được lưu vào `ComponentContext`. Đừng kỳ vọng `getContext().get(id, type)` trả về giá trị đó.

**Đọc giá trị của nhánh chưa chạy.** Component bị bỏ qua không nhất thiết có kết quả. Kiểm tra nhánh và giá trị `null` trước khi dùng.

**Dùng chung builder đã tích lũy component.** Nếu tạo nhiều flow từ builder được dùng lại, hãy `clone().reset()` trước khi khai báo flow mới.

**Chỉ test hàm điều hướng.** Unit test không phát hiện lỗi prompt, thứ tự nhập hoặc cấu hình component. Bổ sung test tương tác bằng `ShellTestClient`.

**Không chờ terminal cập nhật.** Test shell có tính bất đồng bộ. Chờ prompt hoặc output với timeout hữu hạn trước khi gửi input tiếp theo hoặc assert.

**Chỉ assert thông báo.** Hãy xác minh side effect bằng mock hoặc trạng thái dữ liệu để chắc chắn thao tác đã bị hủy thật.

## 12. Checklist trước khi hoàn tất flow

- [ ] Mỗi component có ID duy nhất và dễ nhận biết.
- [ ] Thứ tự mặc định của builder phù hợp với luồng mong muốn.
- [ ] Mỗi `next(...)` chỉ trả về ID hợp lệ hoặc `null` có chủ đích.
- [ ] Các nhánh có kiểm thử riêng cho từng kết quả.
- [ ] Hàm điều hướng không gọi service và không tạo side effect.
- [ ] Xác nhận cho thao tác nguy hiểm có `defaultValue(false)`.
- [ ] Phân biệt `defaultValue`, `resultValue` và `ResultMode`.
- [ ] Chỉ dùng `ResultMode.ACCEPT` khi thực sự muốn bỏ qua input.
- [ ] `storeResult` được bật khi ứng dụng cần đọc giá trị từ flow context.
- [ ] Kết quả `confirm` được kiểm tra trước khi gọi service.
- [ ] Nhánh bị bỏ qua không được giả định có kết quả.
- [ ] Có unit test cho hàm điều hướng.
- [ ] Có interactive test bằng `@ShellTest` và `ShellTestClient`.
- [ ] Test xác minh cả thông báo và side effect.
- [ ] Test terminal bất đồng bộ có timeout hữu hạn.
- [ ] Mỗi lần tạo flow mới đều bắt đầu từ builder đã reset.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 3.3.3 — Flow](https://www.spring-doc.cn/spring-shell/3.3.3/components_flow_index.en.html): thứ tự chạy component, điều hướng bằng `next(...)` và kết quả `ComponentFlowResult`.
- [Spring Shell 3.3 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.Builder.html): tạo, clone, reset và thêm component vào flow.
- [Spring Shell 3.3 API — ComponentFlowResult](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html): lấy context sau khi flow chạy.
- [Spring Shell 3.3 API — StringInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html): `defaultValue`, `resultValue`, `resultMode`, `storeResult` và `next`.
- [Spring Shell 3.3 API — ConfirmationInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html): giá trị mặc định, lưu kết quả và điều hướng sau xác nhận.
- [Spring Shell 3.3 API — ResultMode](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ResultMode.html): khác biệt giữa `ACCEPT` và `VERIFY`.
- [Spring Shell 3.3 API — ComponentContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/context/BaseComponentContext.html): đọc và ghi kết quả trong context.
- [Spring Shell 3.3 API — ShellTest](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/autoconfigure/ShellTest.html), [ShellTestClient](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html) và [ShellWriteSequence](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellWriteSequence.html): mô phỏng phiên terminal và input trong kiểm thử.
- [Spring Shell 3.3 API — ShellAssertions](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellAssertions.html): kiểm tra nội dung hiển thị trên shell screen.

Khi kiểm thử `ComponentFlow`, hãy kiểm tra đồng thời đường đi, dữ liệu được lưu và tác động nghiệp vụ. `next(...)` quyết định flow tiếp tục hay dừng; `defaultValue(...)` định hình lựa chọn ban đầu; `ResultMode` quyết định giá trị có cần người dùng xác minh hay được tự chấp nhận. Một thao tác chỉ nên được thực hiện sau khi flow kết thúc với kết quả xác nhận hợp lệ.

