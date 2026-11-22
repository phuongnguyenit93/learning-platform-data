# Tenant isolation testing: kiểm thử ranh giới dữ liệu và hành động giữa các tenant

Trong chương **Tenant Isolation**, kiểm thử cô lập tenant nhằm chứng minh một chủ thể không thể đọc, sửa hoặc tạo hiệu ứng trên dữ liệu nằm ngoài phạm vi tenant được phép. Việc ứng dụng có cột `tenant_id` hoặc có một bài kiểm thử trả `403` chưa đủ chứng minh ranh giới này được giữ trên toàn bộ luồng nghiệp vụ.

Trong module bảo vệ logic nghiệp vụ, các ca kiểm thử còn phải phát hiện duyệt sai đối tượng, liên kết dữ liệu khác tổ chức, dùng kết quả cache sai phạm vi và tạo tác dụng phụ trước khi bị từ chối. Vì vậy, cần kiểm tra cả response, dữ liệu bền vững và những hệ thống được gọi ra ngoài.

Bài học sử dụng hệ thống đề nghị mua hàng với hai tenant A và B. Các ví dụ là thiết kế kiểm thử và mã minh họa để thích nghi với hợp đồng API thực tế; chúng không phải báo cáo rằng một hệ thống cụ thể đã được kiểm thử.

Sau bài này, bạn có thể:

- Tạo fixture khiến các lỗi thiếu tenant scope dễ xuất hiện.
- Xây dựng ca đối chứng để một kết quả từ chối có ý nghĩa.
- Kiểm tra truy cập trực tiếp, quan hệ, truy vấn tổng hợp và thao tác hàng loạt.
- Phát hiện tác dụng phụ trái phép dù API trả lỗi.
- Kiểm thử cache, worker, context bất đồng bộ và connection pool.
- Đánh giá độ mạnh của bộ kiểm thử khi thêm bảng, endpoint hoặc đường thực thi mới.

## 1. Xác định điều cần chứng minh trước khi viết test

Với một request nghiệp vụ đã được xác lập scope A, các invariant có thể gồm:

```text
response không tiết lộ dữ liệu riêng của B
bản ghi của B không bị tạo, sửa hoặc xóa trái phép
không gắn tài nguyên của B vào đối tượng của A trái chính sách
không phát sinh operation hoặc message tác động tới B ngoài thẩm quyền
cache và dữ liệu xuất không vượt ranh giới quyền
thiếu tenant context không trở thành quyền truy vấn toàn cục
```

Cần xác định thêm dữ liệu nào thực sự dùng chung và đường quản trị nào được phép xuyên tenant. Không viết một quy tắc chung “mọi truy cập khác tenant đều sai” nếu có chức năng quản trị hoặc chia sẻ được cấp quyền rõ ràng.

Tenant isolation cũng không đồng nghĩa mọi người trong cùng tenant có quyền như nhau. Kiểm thử quyền theo đối tượng, bộ phận và trường dữ liệu vẫn cần thiết; một ca đúng tenant nhưng sai chủ sở hữu giúp phân biệt các lớp bảo vệ.

Với tài nguyên dùng chung về mặt hạ tầng, không thể suy rằng hai tenant không bao giờ ảnh hưởng hiệu năng của nhau. Ở đây cần kiểm chứng các ranh giới logic đã định, chẳng hạn quota riêng của A không bị tính nhầm vào B, rồi đánh giá năng lực hạ tầng bằng nhóm kiểm thử phù hợp khác.

## 2. Chuẩn bị fixture có khả năng làm lộ lỗi

Sử dụng dữ liệu tổng hợp trong môi trường kiểm thử được kiểm soát. Hai tenant cần có cấu trúc nghiệp vụ tương tự để lỗi không bị che bởi khác biệt không liên quan.

| Thành phần | Tenant A | Tenant B | Mục đích |
| --- | --- | --- | --- |
| Người dùng có quyền đọc và duyệt | `user-a` | `user-b` | Cùng mức vai trò trong phạm vi riêng |
| Đề nghị đang chờ duyệt | `request-a` | `request-b` | Trạng thái đều hợp lệ cho cùng hành động |
| Nhà cung cấp | `supplier-a` | `supplier-b` | Kiểm tra gán quan hệ chéo tenant |
| Tệp đính kèm | `attachment-a` | `attachment-b` | Kiểm tra đọc gián tiếp và URL tải |
| Ghi chú hoặc dữ liệu đánh dấu | `CANARY_A_...` | `CANARY_B_...` | Nhận biết dữ liệu sai phạm vi trong response |
| Quota hoặc phần giữ | Theo A | Theo B | Kiểm tra tác động lên số liệu và tài nguyên |

Nếu ID chỉ cần duy nhất trong tenant, cố ý tạo cùng ID cục bộ ở hai tenant. Ví dụ cả A và B có `request-001`, nhưng dữ liệu nhận diện khác nhau. Điều này làm truy vấn chỉ dùng `id` dễ trả nhầm hoặc trả nhiều bản ghi.

Nếu mô hình bắt buộc ID duy nhất toàn cục, giữ đúng ràng buộc đó và thử dùng ID thật của B từ scope A. Không sửa schema thành một mô hình không thể xảy ra chỉ để tạo lỗi giả.

Canary là chuỗi tổng hợp dễ nhận diện, không phải dữ liệu thật của khách hàng. Đặt nó trong trường mà người của tenant tương ứng được đọc, và không gửi chính chuỗi đó trong request tấn công thử nghiệm để tránh nhầm dữ liệu phản chiếu với dữ liệu bị đọc.

## 3. Tạo đủ loại chủ thể và ngữ cảnh

Một bộ fixture hữu ích có các chủ thể:

- User A chỉ có membership ở A.
- User B chỉ có membership ở B.
- User AB có membership ở cả hai nhưng mỗi request chọn một scope cụ thể.
- User A có quyền thấp hơn hoặc chỉ được xem một bộ phận trong A.
- User có membership bị khóa hoặc đã bị thu hồi theo chính sách.
- Service principal được phép xử lý một loại công việc trong phạm vi xác định.
- Chủ thể quản trị xuyên tenant có quyền và đường truy cập riêng.

User AB đặc biệt quan trọng. Khi user này đang thao tác trong scope A, body chứa ID đối tượng của B không được tự biến request thành scope B. Một thao tác chuyển scope B hợp lệ lại phải được kiểm thử thành công theo hợp đồng.

Không chỉ thử bằng một token đã sửa payload và mất chữ ký hợp lệ. Ca đó thường chứng minh xác thực token hoạt động, chưa chứng minh phân quyền tenant. Ca mạnh hơn là token hợp lệ của user A truy cập một ID thật và hợp lệ của B.

Với thu hồi membership, xác định rõ mốc hiệu lực và cửa sổ lan truyền mà hệ thống cam kết. Test cần so sánh với hợp đồng đó, không mặc định mọi mô hình token có thu hồi tức thời.

## 4. Mỗi ca từ chối cần một ca đối chứng hợp lệ

Một request trả `404` có thể do route sai, ID không tồn tại, fixture chưa được tạo hoặc tenant isolation thực sự hoạt động. Để phân biệt, thiết kế một nhóm đối chứng:

```text
user A + scope A + request A → thành công
user B + scope B + request B → thành công
user A + scope A + request B → bị chặn theo hợp đồng
```

Với hành động duyệt, cần bảo đảm request B đang chờ duyệt, số tiền nằm trong hạn mức và user B có thể duyệt một fixture tương đương. Nếu request B đã kết thúc hoặc payload sai schema, kết quả từ chối chưa kiểm tra đúng ranh giới tenant.

Nên dùng fixture mới hoặc tách bản ghi đối chứng khi thao tác làm thay đổi trạng thái. Không duyệt B ở bước đối chứng rồi dùng chính bản ghi đã duyệt để chứng minh A không duyệt được B.

Hợp đồng cần chọn mã lỗi và nội dung phù hợp. Nếu API quy định trả `404` cho tài nguyên ngoài scope, test nên kiểm tra chính xác điều đó; không chấp nhận mọi mã lỗi từ `400` đến `599` rồi coi là an toàn.

## 5. Lập ma trận đầu vào có thể chọn hoặc tham chiếu tenant

| Vị trí đầu vào | Biến thể cần thử | Điều cần xác minh |
| --- | --- | --- |
| ID trên route | Thay ID của A bằng ID thật của B | Không đọc hoặc tác động tới B |
| Tenant trên route hoặc header | Chọn tenant ngoài membership | Không tạo scope trái phép |
| Body | Gửi `tenantId`, chủ sở hữu hoặc quan hệ của B | Không ghi đè scope máy chủ đã xác lập |
| Query string | Thêm bộ lọc tenant, tìm kiếm hoặc mở rộng quan hệ | Không làm rộng phạm vi bắt buộc |
| Route cha–con | Cha A và attachment B | Phải kiểm tra quan hệ, không chỉ từng ID |
| Danh sách ID | Trộn A, B và ID không tồn tại | Đúng hợp đồng hàng loạt và không lộ mục ngoài quyền |
| Cursor hoặc page token | Dùng token tạo ở A trong scope B | Không chuyển ngữ cảnh phân trang ngầm |
| Message hoặc callback | Tenant và resource không khớp operation | Không dùng credential service để xử lý thay |

Nếu hệ thống hỗ trợ nhiều nguồn biểu diễn tenant, thử cả trường hợp chúng mâu thuẫn. Ví dụ route chọn A nhưng header chọn B. Hợp đồng phải xác định từ chối hay xử lý theo một nguồn được quy định; các lớp kiểm tra và thực thi không được hiểu khác nhau.

Không giả định body luôn được phép chứa `tenantId`. Nếu đó là trường không được hỗ trợ, kỳ vọng đúng có thể là từ chối schema và không thay đổi dữ liệu. Cần một ca riêng chứng minh caller không thể chọn tenant khác qua nguồn mà API thực sự sử dụng.

## 6. Kiểm thử đọc: dữ liệu, cấu trúc và metadata

Đọc chi tiết là điểm bắt đầu, nhưng bộ kiểm thử cần bao phủ:

- Danh sách và từng trang kết quả.
- Tìm kiếm, gợi ý và bộ lọc có nhánh `OR`.
- `COUNT`, tổng theo trạng thái, nhóm và các thống kê phụ.
- Quan hệ mở rộng, ghi chú, lịch sử duyệt và tài liệu liên kết.
- Tham số chọn trường hoặc các truy vấn lồng nhau.
- Thông báo lỗi, cursor, `totalCount` và metadata có thể tiết lộ thông tin.

Một oracle tốt không chỉ tìm canary. Nó còn so tập ID được trả với tập dữ liệu A mà fixture cho phép, kiểm tra schema phản hồi và giá trị tổng hợp kỳ vọng được tính độc lập.

Ví dụ test danh sách:

```text
fixture A có 2 đề nghị chờ duyệt
fixture B có 5 đề nghị chờ duyệt

GET danh sách trong scope A:
  mọi ID thuộc tập được phép của A
  totalCount bằng số lượng kỳ vọng của A theo bộ lọc
  không có CANARY_B
  trang tiếp theo vẫn giữ cùng phạm vi
```

Không chỉ kiểm tra số lượng bằng 2: API có thể trả hai bản ghi sai tenant. Cũng không chỉ kiểm tra mọi ID đều thuộc A: `totalCount = 7` vẫn làm lộ dữ liệu ngoài phạm vi.

Với tín hiệu thời gian, không kết luận không có rò rỉ chỉ vì hai request có độ trễ gần nhau trong một lần chạy. Những kênh suy luận qua timing cần phương pháp đo và phân tích riêng; các oracle xác định về dữ liệu và hiệu ứng nên là nền tảng trước.

## 7. Minh họa Java: một phép thử HTTP có đối chứng

Ví dụ sau giả định hợp đồng dùng header `X-Tenant-ID`, token cá nhân hợp lệ và trả `404` khi đối tượng ngoài scope. Mã dùng Java 17 với HTTP client có sẵn, không phụ thuộc framework test. Endpoint và fixture phải được thay bằng dữ liệu của hệ thống kiểm thử.

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

record TenantIdentity(String accessToken, String tenantId) {
}

record IsolationFixture(
        TenantIdentity userA,
        TenantIdentity userB,
        String requestA,
        String requestB,
        String canaryB) {
}

final class TenantReadProbe {
    private TenantReadProbe() {
    }

    static void verify(URI baseUri, IsolationFixture fixture)
            throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpResponse<String> ownA = get(
                client, baseUri, fixture.userA(), fixture.requestA());
        check(ownA.statusCode() == 200, "Control A failed");

        HttpResponse<String> ownB = get(
                client, baseUri, fixture.userB(), fixture.requestB());
        check(ownB.statusCode() == 200, "Control B failed");
        check(ownB.body().contains(fixture.canaryB()),
                "Control B did not expose its expected test marker");

        HttpResponse<String> cross = get(
                client, baseUri, fixture.userA(), fixture.requestB());
        check(cross.statusCode() == 404,
                "Cross-tenant response violated the API contract");
        check(!cross.body().contains(fixture.canaryB()),
                "Cross-tenant test marker was disclosed");
    }

    private static HttpResponse<String> get(
            HttpClient client,
            URI baseUri,
            TenantIdentity identity,
            String requestId) throws Exception {
        // Fixture IDs are safe path segments generated by the test setup.
        URI uri = baseUri.resolve("/api/purchase-requests/" + requestId);
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Authorization", "Bearer " + identity.accessToken())
                .header("X-Tenant-ID", identity.tenantId())
                .GET()
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Hàm `check` luôn hoạt động, không phụ thuộc việc bật Java assertions. Test không in token vào thông báo lỗi và không tự đi theo redirect làm che lấp hợp đồng của endpoint.

Đây chỉ là một phép thử đọc tối thiểu. Trong bộ kiểm thử thực tế, cần phân tích JSON bằng công cụ phù hợp để kiểm tra ID, tập trường và dữ liệu lồng nhau; tìm chuỗi canary không thay thế toàn bộ oracle.

## 8. Kiểm thử ghi bằng snapshot trước–sau

Một API có thể trả lỗi sau khi đã sửa dữ liệu hoặc tạo message. Vì vậy, ca ghi cần một nguồn quan sát độc lập với chính đường repository đang được kiểm thử.

Trong môi trường test, có thể lấy snapshot bằng kết nối kiểm tra được phép đọc các fixture liên quan:

```sql
SELECT tenant_id, id, state, version, supplier_id
FROM purchase_request
WHERE tenant_id IN (:fixture_tenant_a, :fixture_tenant_b)
ORDER BY tenant_id, id;
```

Đây là truy vấn phục vụ oracle kiểm thử trên dữ liệu tổng hợp. Nó không phải mẫu cho endpoint nghiệp vụ xuyên tenant.

Mẫu một ca ghi bị cấm:

```text
before = snapshot các fixture A, B và dữ liệu phụ liên quan
externalBefore = số yêu cầu mà fake provider đã nhận

gọi hành động lên đối tượng B bằng actor và scope A

kiểm tra mã lỗi và response theo hợp đồng
after = đọc snapshot độc lập
kiểm tra đối tượng B, version và quan hệ không đổi
kiểm tra không có quyết định hoặc đơn mới cho B
kiểm tra không có outbox thực hiện trái phép
kiểm tra fake provider không nhận thêm yêu cầu
```

Không dùng cùng một phương thức đang thiếu tenant scope làm oracle rồi kết luận dữ liệu không đổi vì phương thức đó không nhìn thấy bản ghi bị ảnh hưởng. Oracle cần truy vấn fixture theo định danh và phạm vi được xác định độc lập.

Các bản ghi nhật ký về một lần bị từ chối có thể được phép xuất hiện. Cần phân biệt chúng với audit thành công, quyết định duyệt hoặc tác dụng phụ nghiệp vụ không được phép.

## 9. Kiểm thử quan hệ và ràng buộc cơ sở dữ liệu

Những ca cần có:

| Hành động | Biến thể trái phép | Điều cần kiểm tra |
| --- | --- | --- |
| Tạo đề nghị ở A | Dùng `supplierId` của B | Không lưu quan hệ chéo tenant |
| Đọc tệp của đề nghị A | Đưa `attachmentId` của B | Không trả bytes hoặc URL tải của B |
| Đọc phiếu duyệt | Vòng duyệt B gắn vào route đề nghị A | Không chấp nhận các ID không cùng quan hệ |
| Thêm ghi chú | Tham chiếu parent B trong body của request A | Không tạo bản ghi ở sai parent hoặc tenant |
| Sửa đối tượng | Gửi `tenantId` mới hoặc đổi chủ sở hữu sang B | Không di chuyển dữ liệu qua patch thông thường |

Thêm cả ca cha–con sai nhưng cùng tenant. Một API chỉ kiểm tra tenant mà không kiểm tra attachment thuộc đúng parent vẫn có thể vi phạm quyền theo đối tượng.

Ở tầng cơ sở dữ liệu, kiểm thử khóa ngoại tổng hợp hoặc cơ chế tương ứng bằng dữ liệu quan hệ không hợp lệ. Nếu ràng buộc chặn được, xác minh transaction không để lại phần dữ liệu khác đã ghi trước đó.

Tầng API vẫn cần phản hồi đúng hợp đồng. Một lỗi `500` từ constraint có thể chặn việc lưu nhưng chưa chứng minh API xử lý quyền đúng, không lộ tên hoặc dữ liệu nội bộ và không gọi hệ thống ngoài trước khi lỗi xảy ra.

## 10. Kiểm thử hàng loạt, thống kê và quota

Với lệnh xử lý hàng loạt, tạo danh sách gồm ID hợp lệ của A, ID thật của B và ID không tồn tại. Chọn kỳ vọng theo hợp đồng:

- Nếu toàn bộ hoặc không gì cả, không mục nào được commit khi lô không hợp lệ.
- Nếu xử lý từng mục, chỉ mục được phép mới thay đổi và lỗi không tiết lộ dữ liệu ngoài quyền.
- Việc lặp ID không tạo thêm tác dụng phụ hoặc làm sai số lượng kiểm tra.
- Quyền bộ phận và trạng thái được đánh giá cho từng mục, không kế thừa từ mục đầu tiên.

Với thống kê, fixture nên tạo chênh lệch rõ giữa A và B để phép đếm toàn cục dễ bị phát hiện. Thử bộ lọc rỗng, nhiều nhánh OR, tìm kiếm và các nhánh hợp nhất dữ liệu mà endpoint hỗ trợ.

Với quota riêng tenant, xác minh một hoạt động hợp lệ ở A chỉ thay đổi sổ và bộ đếm của A. Quota toàn hệ thống nếu có là một quy tắc khác; không coi mọi ảnh hưởng dùng chung là lỗi mà chưa đối chiếu chính sách.

Đặc biệt thử cùng mã nghiệp vụ cục bộ ở hai tenant. Một khóa unique hoặc khóa tác vụ thiếu tenant có thể làm request B bị xung đột bởi dữ liệu A dù không làm lộ một bản ghi trực tiếp.

## 11. Cache và idempotency phải được kiểm thử qua thứ tự truy cập

Một test chỉ gọi API trên cache rỗng có thể bỏ sót lỗi nghiêm trọng. Hãy thay đổi thứ tự:

```text
làm nóng cache bằng user A, scope A
đọc bằng user B, scope B
thử đọc ID của A từ scope B

xóa hoặc tái tạo fixture cache
làm nóng theo chiều B rồi A
lặp lại các kiểm tra
```

Với ID cục bộ giống nhau, cache key chỉ có ID thường dễ bị phát hiện. Với ID toàn cục, vẫn phải thử truy cập bằng người không có quyền sau khi cache đã chứa response hoặc entity, vì cache không được bỏ qua bước phân quyền.

Kiểm tra cả cache danh sách, projection theo vai trò, quan hệ lồng nhau và bộ gom tải dữ liệu. User A và B có cùng mức vai trò giúp ca tenant không bị nhầm với khác biệt về quyền trường; sau đó thêm các ca quyền trường riêng.

Với idempotency, user AB có thể gửi cùng key trong hai scope khác nhau nếu hợp đồng định nghĩa key riêng theo tenant. Cả hai thao tác hợp lệ phải có kết quả độc lập và đúng tenant, không trả kết quả cũ của scope kia hoặc xung đột do một cache toàn cục sai ngữ nghĩa.

Đồng thời kiểm tra cùng key nhưng đổi đối tượng trong cùng phạm vi, retry cùng ý định và key khác trên cùng operation. Cô lập tenant không được làm mất các invariant chống thực hiện trùng của từng tenant.

## 12. Worker, callback và tác dụng phụ bên ngoài

Một hàng đợi có thể vận chuyển message hợp lệ về cú pháp nhưng mâu thuẫn về thẩm quyền:

```text
tenantId = A
resourceId = request của B
operationId = operation thuộc B
```

Test cần xác minh consumer không dùng credential rộng để xử lý message như thể mọi trường đều đáng tin. Nguồn phát, loại công việc và phạm vi tenant mà nguồn được phép xác nhận là một phần của dữ liệu kiểm thử.

Các ca chính:

- Message chỉ có resource ID mà thiếu tenant bắt buộc.
- Tenant hợp lệ nhưng operation hoặc snapshot không cùng quan hệ.
- Event gửi lặp hoặc có cùng ID cục bộ ở tenant khác.
- Callback đúng định dạng nhưng khớp operation của tenant khác.
- Worker xử lý A rồi lỗi, sau đó nhận công việc B trên cùng luồng.
- Một message cũ đến sau khi quyền hoặc trạng thái đã thay đổi.

Dùng fake provider hoặc test double ở biên ngoài để thu request đã nhận, gồm operation và phạm vi nghiệp vụ cần đối chiếu. Kiểm tra không có lời gọi trái phép, không chỉ kiểm tra trạng thái nội bộ sau rollback.

Nếu hệ thống đã ghi một operation hợp lệ trước một thay đổi quyền, kỳ vọng tiếp tục hay dừng phải theo hợp đồng của operation. Không gộp mọi message đến muộn thành tấn công tenant, nhưng luôn kiểm tra nó vẫn được gán cho đúng tenant và đối tượng.

## 13. Context bất đồng bộ và kết nối dùng lại

Connection pool và thread pool có thể làm một test tuần tự đơn giản không đủ nhạy. Cần cố tình tạo lịch dùng lại:

```text
request A thành công
request A gặp exception trước bước dọn context
request B chạy trên tài nguyên dùng lại
request thiếu scope chạy tiếp theo
```

Kỳ vọng là B chỉ dùng B, còn request thiếu scope bị xử lý theo hợp đồng thay vì nhận scope còn sót của A hoặc B.

Trong môi trường tích hợp, có thể cấu hình pool rất nhỏ hoặc một worker đơn để tăng khả năng dùng lại cùng connection hoặc thread. Sau đó có nhóm test chạy song song với nhiều tài nguyên để phát hiện nhầm context giữa request.

Nếu dùng biến phiên cơ sở dữ liệu hoặc row-level security, chạy kiểm thử bằng cùng kiểu tài khoản và quyền mà ứng dụng thực tế sử dụng. Một tài khoản test có đặc quyền khác có thể làm kết quả không đại diện cho môi trường triển khai.

Với schema hoặc database riêng tenant, xác minh lựa chọn kết nối đúng và không fallback khi mapping thiếu. Oracle có thể dùng instrumentation kiểm thử để biết nơi dữ liệu được ghi, không cần đưa chi tiết hạ tầng nhạy cảm vào response sản phẩm.

Tranh chấp cần điểm đồng bộ có chủ đích, chẳng hạn chặn sau lúc đọc context rồi cho request khác chạy. Chỉ thêm `sleep` không bảo đảm đã tạo đúng lịch thực thi và dễ làm test chập chờn.

## 14. Tệp xuất, đường tải và dữ liệu ngoài response chính

Kiểm thử một job xuất nên bao gồm toàn bộ vòng đời:

```text
tạo job trong scope A
worker chạy job
tệp được ghi
user có quyền tải tệp
user B hoặc scope B thử truy cập job và tệp đó
```

Kiểm tra nội dung tệp bằng oracle fixture, không chỉ tên tệp hoặc metadata job. Một truy vấn đúng tenant ở endpoint tạo job không chứng minh truy vấn bên worker đúng tenant.

Các đường khác cũng cần nằm trong danh mục kiểm thử:

- URL tải được ký và cơ chế kiểm tra quyền trước khi cấp URL.
- Email hoặc webhook theo tenant và người nhận được phép.
- Search index và bản chiếu báo cáo.
- Subscription hoặc kết nối dài chuyển dữ liệu sau lần xác thực đầu.
- Cache ở proxy hoặc lớp phân phối phản hồi.
- Log và giao diện audit mà người dùng tenant có thể xem.

Đánh giá dữ liệu đã được cấp ra ngoài theo khả năng của hệ thống. Test không nên đòi thu hồi một bản sao đã tải về chỉ bằng thay đổi permission, nhưng cần kiểm tra khả năng truy cập mới theo hợp đồng đã công bố.

## 15. Chọn đúng tầng kiểm thử

| Tầng | Điều có thể kiểm chứng tốt | Điều chưa đủ để kết luận |
| --- | --- | --- |
| Unit policy | Quy tắc scope, membership và điều kiện quyền | SQL và cấu hình thực tế có thực thi quy tắc không |
| Repository với DB phù hợp | Predicate, join, constraint và transaction | Token, route hoặc message có tạo đúng context không |
| API tích hợp | Kết hợp xác thực, scope, query và response | Mọi đường ngoài API chính đều đã được bao phủ |
| Worker và biên ngoài | Ngữ cảnh message, chống lặp và tác dụng phụ | Giao diện người dùng hoặc endpoint khác cũng đúng |
| Luồng xuyên thành phần | Chuỗi job, tệp, callback và cache | Mọi lịch cạnh tranh đều đã được thử |

Không chỉ mock repository trả dữ liệu A rồi khẳng định service không trả dữ liệu B. Test đó có thể đúng với policy nhưng không phát hiện repository thật bỏ điều kiện tenant.

Ngược lại, một test SQL đúng không chứng minh tầng HTTP không lấy tenant từ body không được xác minh. Các lớp cần bổ sung cho nhau theo ranh giới thực tế.

Chọn cơ sở dữ liệu và cơ chế quyền phù hợp cho những ca dựa vào khóa, transaction hoặc chính sách hàng. Một môi trường thay thế có ngữ nghĩa khác cần được nhận diện là giới hạn của bằng chứng, không được coi như tương đương mặc định.

## 16. Đánh giá độ mạnh và mở rộng bộ kiểm thử

Một danh mục kiểm thử nên được xây từ hợp đồng nghiệp vụ và các đường dữ liệu, không chỉ sinh từ chính điều kiện hiện có trong mã. Nếu mã thiếu một nhánh bảo vệ và test cũng lấy cùng cấu hình thiếu đó làm chuẩn, cả hai có thể cùng sai.

Các cách tăng độ nhạy:

- Tham số hóa các cặp actor–scope–resource trên nhiều tenant tổng hợp.
- Tạo dữ liệu giống nhau về vai trò, trạng thái và loại đối tượng để cô lập biến tenant.
- Sinh các tổ hợp parent–child, danh sách ID và thứ tự cache khác nhau.
- Giữ bảng kỳ vọng độc lập về tập bản ghi, trường và tác dụng phụ được phép.
- Khi thêm bảng con, endpoint, báo cáo hoặc worker, bổ sung đường đó vào danh mục.

Có thể đánh giá bằng mutation testing trong nhánh kiểm thử: cố ý bỏ một tenant predicate hoặc làm sai cache key để xem nhóm test phù hợp có phát hiện không. Đây là cách kiểm tra độ nhạy, không phải thay đổi cấu hình sản phẩm để giảm bảo vệ.

Nếu một lớp phòng vệ khác vẫn giữ invariant, mutation ở một lớp có thể chưa tạo lỗi quan sát được ở tầng API. Khi đó cần đánh giá ở đúng tầng và hiểu phần bảo vệ còn lại, không mặc định mọi dòng tenant predicate phải độc lập làm một test đầu cuối thất bại.

Các ca sinh ngẫu nhiên cần có seed hoặc dữ liệu tái hiện. Khi phát hiện lỗi, thu nhỏ thành fixture và lịch thực thi cụ thể để sửa và giữ làm regression test.

## 17. Ghi nhận kết quả và tránh kết luận sai

Một kết quả kiểm thử hữu ích nên có:

```text
actor và scope đã xác minh trong fixture
đối tượng đích và tenant thật của nó
ca đối chứng chứng minh route, dữ liệu và hành động hợp lệ
request được gửi và hợp đồng kết quả mong đợi
response thực tế cùng phép kiểm tra cấu trúc và metadata
chênh lệch dữ liệu trước–sau
outbox, operation và lời gọi biên ngoài có liên quan
lịch đồng thời hoặc thứ tự cache nếu có
phiên bản cấu hình, schema và điều kiện chạy cần để tái hiện
```

Không ghi token hoặc credential đầy đủ vào báo cáo. Dùng định danh fixture và thông tin đủ để tái hiện trong môi trường được kiểm soát.

Những kết luận cần tránh:

| Kết luận vội | Vấn đề |
| --- | --- |
| “Trả 404 nên không thể vượt tenant” | Chưa có đối chứng và chưa quan sát hiệu ứng phụ |
| “Không thấy canary nên không rò rỉ” | Có thể rò ID, số lượng, trường khác hoặc đường tải |
| “DB không đổi nên an toàn” | Lời gọi ngoài hoặc message có thể đã được tạo |
| “Có RLS nên không cần test API” | Context và quyền tài khoản DB có thể sai |
| “UUID không đoán được nên không cần ca chéo tenant” | Biết ID không được biến thành quyền truy cập |
| “Hai test chạy song song đã phủ concurrency” | Có thể chưa tạo đúng cửa sổ cần kiểm tra |
| “Mọi truy cập xuyên tenant đều phải thất bại” | Có thể bỏ qua đường quản trị hợp lệ đã được cấp quyền |

Ghi rõ phạm vi đã kiểm thử và giới hạn còn lại. Các tín hiệu vận hành như truy vấn thiếu scope, lỗi quan hệ chéo tenant hoặc worker không có context có thể bổ sung bằng chứng sau triển khai, nhưng không thay thế bộ kiểm thử trước thay đổi.

## 18. Quy trình áp dụng vào một tính năng mới

1. Xác định dữ liệu tenant-owned, dữ liệu dùng chung và các hành động được phép xuyên tenant.
2. Tạo ít nhất hai tenant với đối tượng hợp lệ, vai trò tương đương và dữ liệu đánh dấu riêng.
3. Viết ca đối chứng thành công trước khi viết ca chéo tenant bị từ chối.
4. Lập ma trận nguồn chọn tenant, ID trực tiếp, quan hệ và truy vấn gián tiếp.
5. Kiểm tra response cùng snapshot dữ liệu, operation, outbox và biên ngoài.
6. Bổ sung hàng loạt, thống kê, quota, idempotency, cache và tệp xuất.
7. Ép dùng lại connection hoặc thread, rồi tạo lịch cạnh tranh có kiểm soát.
8. Chạy ở đúng các tầng API, repository, cơ sở dữ liệu và worker mà tính năng sử dụng.
9. Lưu ca tái hiện và oracle độc lập làm regression test khi sửa lỗi hoặc mở rộng đường truy cập.

Kiểm thử cô lập tenant có sức thuyết phục khi chỉ ra đúng ai đang hành động, phạm vi nào đã được xác minh và mọi dữ liệu hoặc hiệu ứng có tuân thủ phạm vi đó không. Ca đối chứng, oracle độc lập và quan sát toàn bộ tác dụng phụ giúp phát hiện những lỗi mà một mã HTTP từ chối đơn lẻ không thể chứng minh.
