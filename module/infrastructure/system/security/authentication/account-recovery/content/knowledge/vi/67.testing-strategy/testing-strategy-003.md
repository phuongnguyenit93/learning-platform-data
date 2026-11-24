# Recovery contract tests

## 1. Contract test bảo vệ điều gì trong luồng khôi phục?

**Recovery contract tests** kiểm chứng rằng bên cung cấp và bên sử dụng một API hoặc sự kiện cùng hiểu đúng cấu trúc, ý nghĩa và các cam kết quan sát được của giao tiếp đó. Trong luồng khôi phục tài khoản, một thay đổi nhỏ ở hợp đồng có thể khiến client cấp quyền quá sớm, gửi cảnh báo sai đối tượng hoặc làm lộ sự tồn tại của tài khoản.

Ví dụ, một consumer hiểu sự kiện `RecoveryInitiated` là “đã ghi nhận yêu cầu”, trong khi một phiên bản khác bắt đầu diễn giải nó là “người dùng đã được xác minh”. Hai phía vẫn trao đổi JSON hợp lệ nhưng đang hiểu khác nhau về quyền được phép thực hiện. Contract test cần giúp phát hiện loại thay đổi ý nghĩa này, không chỉ lỗi thiếu field.

Một hợp đồng khôi phục thường phải trả lời:

- Bên nào có quyền cung cấp dữ liệu hoặc xác lập một sự kiện?
- Request hoặc payload có cấu trúc và giới hạn gì?
- Phản hồi nào xuất hiện trong từng trạng thái đã định?
- Trạng thái đó cho phép client hoặc consumer làm gì?
- Dữ liệu nào tuyệt đối không được đưa ra bề mặt này?
- Thay đổi nào tương thích với những phiên bản đang được hỗ trợ?

Contract test là một phần của chiến lược kiểm thử. Nó không tự chứng minh token được tiêu thụ nguyên tử trong DB, chống được mọi race condition hoặc session đã bị thu hồi trên mọi node.

## 2. Phân biệt contract test với các lớp kiểm thử khác

| Loại kiểm thử | Câu hỏi chính | Ví dụ trong khôi phục tài khoản |
|---|---|---|
| Unit test | Một thành phần xử lý đúng quy tắc cục bộ không? | Mapper chuyển trạng thái nội bộ sang mã phản hồi |
| Contract test | Hai phía có tương thích về giao tiếp và ý nghĩa đã cam kết không? | Provider trả đúng phản hồi công khai cho trạng thái được chuẩn bị |
| Integration test | Những thành phần thật phối hợp đúng ở ranh giới không? | HTTP, DB và kho credential cùng xử lý việc dùng token |
| End-to-end test | Một hành trình rộng có hoạt động theo cấu hình triển khai không? | Người dùng yêu cầu khôi phục, nhận hướng dẫn, xác minh và truy cập lại |

Một contract test có thể chạy provider thật với cơ sở dữ liệu kiểm thử, nên về mặt kỹ thuật nó cũng tích hợp nhiều thành phần. Sự phân biệt ở đây nằm ở mục tiêu: test hợp đồng tập trung vào cam kết giữa hai phía, thay vì bao phủ toàn bộ diễn biến bên trong.

Nếu provider bị thay hoàn toàn bằng một mock được lập trình để trả đúng giá trị mong đợi, test chỉ chứng minh consumer hiểu mock đó. Cần có bước **provider verification** chạy cùng tương tác đã công bố trên phiên bản provider thực sự sẽ được triển khai.

## 3. Các bề mặt cần hợp đồng riêng

Không nên gom mọi giao tiếp thành một schema lớn của “recovery”. Mỗi bề mặt có người đọc và mức tin cậy khác nhau.

| Bề mặt | Những cam kết cần làm rõ |
|---|---|
| API khởi tạo công khai | Phản hồi chống dò tài khoản, dữ liệu được phép tiết lộ và giới hạn đầu vào |
| API theo dõi hồ sơ | Quyền đọc, phạm vi dữ liệu và ý nghĩa trạng thái hiện hành |
| API xác minh hoặc hoàn tất | Capability cần có, mục đích thao tác, phản hồi thành công và lỗi |
| API Identity/Session nội bộ | Quyền bên gọi, ràng buộc tài khoản, tenant và mức tác dụng |
| Sự kiện khôi phục | Nguồn phát, thời điểm nghiệp vụ, schema và ý nghĩa phiên bản |
| Yêu cầu gửi thông báo | Loại thông báo, binding người nhận, hạn gửi và dữ liệu được phép kết xuất |
| Callback từ nhà cung cấp | Cách xác minh nguồn, định danh tác vụ và ý nghĩa tín hiệu chuyển phát |

Hợp đồng cho API công khai không nên tái sử dụng nguyên DTO nội bộ. Một field cần thiết cho Risk Service có thể hoàn toàn không phù hợp để trả cho người chưa xác thực.

Trong bài học, tên endpoint, trạng thái và mã kết quả là ví dụ thiết kế. Chúng không khẳng định module hiện có những API hoặc fixture tương ứng.

## 4. Hợp đồng gồm cấu trúc, ngữ nghĩa và quyền

### 4.1. Cấu trúc

Phần cấu trúc mô tả method, path, header, content type, field bắt buộc, kiểu dữ liệu, kích thước, giá trị cho phép và hình dạng phản hồi. Với sự kiện, cần thêm loại sự kiện, phiên bản schema và định danh liên kết.

Một field dạng chuỗi chưa đủ diễn đạt mọi giới hạn. `requestId`, `locale`, `actionUrl` và `token` đều có thể là chuỗi nhưng có mục đích, cách kiểm tra và yêu cầu bảo vệ rất khác nhau.

### 4.2. Ngữ nghĩa

Ngữ nghĩa trả lời một trạng thái hoặc mã có nghĩa gì. Ví dụ:

| Giá trị | Ý nghĩa hợp lệ | Cách hiểu sai cần chặn |
|---|---|---|
| `REQUEST_ACCEPTED` ở phản hồi công khai | Hệ thống trả thông báo tiếp nhận chung theo hợp đồng | Chắc chắn tồn tại tài khoản tương ứng |
| `WAITING` | Yêu cầu đang trong khoảng chờ theo chính sách | Hết bộ đếm là chắc chắn được khôi phục |
| `READY_FOR_NEXT_STEP` | Có thể thực hiện bước được chỉ định nếu đáp ứng quyền tương ứng | Có quyền thực hiện mọi thay đổi bảo mật |
| `RecoveryInitiated` | Hồ sơ đã được khởi tạo theo hợp đồng của producer | Danh tính người gửi đã được xác minh |
| `NotificationDelivered` | Có tín hiệu chuyển phát theo định nghĩa của kênh | Chủ tài khoản đã đọc và đồng ý khôi phục |

Contract test có thể kiểm tra các ánh xạ và phản ứng của consumer trước các giá trị này. Những quyết định có ảnh hưởng đến tài khoản vẫn cần được thực thi bởi dịch vụ có thẩm quyền, không chỉ bằng điều kiện hiển thị trên client.

### 4.3. Quyền và phân loại dữ liệu

Hợp đồng cần ghi rõ loại credential hoặc capability nào được yêu cầu và dữ liệu nào người gọi được phép thấy. ID tài khoản trong body không thay thế kiểm tra quyền; field `producer` trong JSON không thay thế xác thực nguồn.

Một schema có `additionalProperties: true` có thể phù hợp cho consumer chịu được field bổ sung, nhưng không bảo đảm provider không làm lộ dữ liệu. Nên tách **khả năng đọc tương thích của consumer** khỏi **chính sách xuất dữ liệu của provider**. Phản hồi công khai cần cơ chế giới hạn field theo mục đích, kể cả khi consumer thường bỏ qua field lạ.

## 5. Ví dụ hợp đồng API khởi tạo công khai

Giả sử một API có hợp đồng minh họa sau:

```http
POST /recovery-requests
Content-Type: application/json

{
  "identifier": "user@example.test",
  "declaredLoss": "MFA_DEVICE"
}
```

Khi đầu vào hợp lệ ở mức biểu mẫu và chưa bị giới hạn tần suất, phản hồi công khai không phân biệt có tài khoản tương ứng hay không:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
Cache-Control: no-store

{
  "code": "RECOVERY_REQUEST_ACCEPTED",
  "message": "Nếu thông tin phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký."
}
```

Trong ví dụ, `202` thể hiện phản hồi tiếp nhận theo hợp đồng công khai, không khẳng định một hồ sơ thật đã được tạo cho mọi đầu vào. Provider có thể chỉ tạo hồ sơ khi tài khoản và chính sách nội bộ phù hợp.

### Những điều cần kiểm tra

1. Method, path và content type đúng hợp đồng.
2. Hai provider state “có tài khoản đủ điều kiện” và “không có tài khoản tương ứng” có cùng hình dạng phản hồi công khai và cùng thông điệp ở cùng ngôn ngữ.
3. Không xuất hiện `accountExists`, `accountId`, `mfaEnabled`, địa chỉ nhận đã che một phần hoặc lý do rủi ro nội bộ.
4. Client không dùng `RECOVERY_REQUEST_ACCEPTED` để cấp quyền đi tiếp vào một thao tác nhạy cảm.
5. `Cache-Control` đáp ứng quy tắc không lưu phản hồi đã chọn cho API này.

Hợp đồng vẫn có thể có phản hồi khác cho JSON sai cấu trúc, kích thước vượt giới hạn hoặc giới hạn tốc độ. Cần kiểm tra các trường hợp này riêng và tránh để lý do khác nhau làm lộ trạng thái tài khoản ngoài ý muốn. Không yêu cầu mọi request ở mọi hoàn cảnh đều trả `202`.

Kiểm tra phản hồi giống nhau cũng không chứng minh hai nhánh không có khác biệt thời gian. Phân tích timing cần phép đo và kiểm thử phù hợp trong môi trường được kiểm soát.

## 6. Ví dụ Java kiểm chứng provider qua HTTP thật

Ví dụ dùng JUnit và HTTP client của Java. Đây là lớp test cơ sở: dự án cần cung cấp phần chuẩn bị provider state và bộ phân tích JSON. Phần đó không được thay endpoint đang kiểm tra bằng một mock trả đáp án cố định.

```java
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

abstract class RecoveryInitiationContractTest {
    protected abstract InitiationFixture given(ProviderState state);
    protected abstract Map<String, Object> parseJsonObject(String json);

    private final HttpClient client = HttpClient.newBuilder()
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    @Test
    void publicAcknowledgmentDoesNotRevealAccountExistence()
            throws Exception {
        Map<String, Object> known = invokeAndVerify(
                given(ProviderState.KNOWN_ELIGIBLE_ACCOUNT));
        Map<String, Object> unknown = invokeAndVerify(
                given(ProviderState.UNKNOWN_IDENTIFIER));

        assertEquals(known, unknown);
    }

    private Map<String, Object> invokeAndVerify(InitiationFixture fx)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(fx.endpoint())
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .header("Accept-Language", "vi")
                .POST(HttpRequest.BodyPublishers.ofString(fx.requestJson()))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        assertEquals(202, response.statusCode());

        String mediaType = response.headers()
                .firstValue("Content-Type").orElse("")
                .split(";", 2)[0].trim();
        assertTrue("application/json".equalsIgnoreCase(mediaType));

        String cacheControl = String.join(",",
                response.headers().allValues("Cache-Control"));
        boolean noStore = Arrays.stream(cacheControl.split(","))
                .map(String::trim)
                .anyMatch("no-store"::equalsIgnoreCase);
        assertTrue(noStore);

        Map<String, Object> body = parseJsonObject(response.body());
        assertEquals(Set.of("code", "message"), body.keySet());
        assertEquals("RECOVERY_REQUEST_ACCEPTED", body.get("code"));
        assertInstanceOf(String.class, body.get("message"));
        assertFalse(((String) body.get("message")).isBlank());
        return body;
    }

    enum ProviderState {
        KNOWN_ELIGIBLE_ACCOUNT,
        UNKNOWN_IDENTIFIER
    }

    record InitiationFixture(URI endpoint, String requestJson) {}
}
```

Các giả định của ví dụ:

- `given(...)` chuẩn bị dữ liệu bền vững và đầu vào phù hợp cho từng trạng thái, với endpoint chỉ đến provider kiểm thử.
- `parseJsonObject(...)` dùng một bộ phân tích JSON thực; không so sánh chuỗi JSON theo thứ tự field.
- Cùng ngôn ngữ được dùng ở hai tương tác để phép so sánh không bị ảnh hưởng bởi bản địa hóa.
- Hợp đồng của phản hồi này chỉ cho phép hai field công khai. Nếu bổ sung field, thay đổi cần được xem xét theo phân loại dữ liệu thay vì để consumer bỏ qua và coi là an toàn.
- Thời gian timeout là lựa chọn minh họa cho test, không phải yêu cầu hiệu năng chung của dịch vụ.

Test không cố định nguyên văn câu thông báo vào một hằng số của client; nó kiểm tra câu đó không rỗng và không phân biệt hai trạng thái nội bộ trong cùng ngữ cảnh. Mã `code` mới là giá trị máy có hợp đồng ổn định ở ví dụ này.

Dùng dữ liệu tổng hợp giúp assertion không làm lộ thông tin thật. Trong những test chứa token hoặc bằng chứng, cần tránh để message thất bại dump toàn bộ payload nhạy cảm.

## 7. Provider state phải là trạng thái thật có thể kiểm chứng

Provider state mô tả điều kiện ban đầu cần có để provider trả một kết quả. Ví dụ:

| Provider state | Điều kiện cần chuẩn bị | Điều cần tránh |
|---|---|---|
| Hồ sơ đang chờ | Hồ sơ, mốc thời gian và quyền xem nhất quán | Chỉ mock mapper để ép trả `WAITING` |
| Token còn hiệu lực | Đúng tài khoản, mục đích và trạng thái chưa dùng | Tắt toàn bộ bước kiểm tra token trong profile test |
| Token đã hết hạn | Nguồn thời gian và dữ liệu hạn dùng tương ứng | Chỉ đổi một nhãn fixture trong khi provider vẫn dùng clock thật |
| Không đủ quyền xem hồ sơ | Danh tính thực của người gọi không đáp ứng quyền | Gọi thẳng controller rồi bỏ filter bảo mật |
| Đích thông báo bị thu hồi | Binding và chính sách được chuẩn bị phù hợp | Để mock resolver trả bất kỳ email nào |

Cơ chế thiết lập provider state cần tách khỏi bề mặt production. Nếu dùng API thiết lập nội bộ cho quá trình verification, nó phải chỉ tồn tại hoặc chỉ truy cập được trong môi trường thử với kiểm soát phù hợp; không cung cấp chức năng tạo token hoặc bỏ qua xác minh trên một endpoint công khai.

State cũng cần độc lập giữa các test. Một test không nên dựa vào token đã được test trước tạo ra, vì thay đổi thứ tự chạy có thể làm kết quả không ổn định và che sai lệch hợp đồng.
