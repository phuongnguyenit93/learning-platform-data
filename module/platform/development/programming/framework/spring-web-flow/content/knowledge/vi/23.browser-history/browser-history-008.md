# Snapshot bị loại bỏ do vượt giới hạn lịch sử

Spring Web Flow lưu snapshot của flow execution để có thể khôi phục trạng thái khi người dùng quay lại một URL thực thi cũ trong lịch sử trình duyệt. Tuy nhiên, repository không nhất thiết giữ mọi snapshot từ lúc flow bắt đầu đến khi kết thúc. Khi số snapshot vượt giới hạn cấu hình, những snapshot cũ có thể bị loại bỏ. Trình duyệt vẫn còn URL lịch sử đó, nhưng máy chủ không còn trạng thái tương ứng để khôi phục.

Trong chương **Lịch sử trình duyệt**, bài này giải thích vì sao xảy ra tình huống đó, cách cấu hình giới hạn snapshot, cách phân biệt lỗi snapshot cũ với việc flow execution đã hết hạn và cách thiết kế đường phục hồi. Đây là một phần của việc xây dựng hành trình nhiều bước bằng Spring Web Flow: state và transition cần hỗ trợ thao tác quay lại, đồng thời flow phải giữ dữ liệu vừa đủ và xử lý an toàn khi trạng thái lịch sử không còn.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích vai trò của snapshot trong việc khôi phục flow execution khi dùng Back/Forward.
- Phân biệt giới hạn số snapshot của một execution với giới hạn số execution trong HTTP session.
- Cấu hình `max-execution-snapshots` và chọn giá trị phù hợp với quy trình.
- Nhận biết URL execution cũ trỏ đến snapshot đã bị loại bỏ.
- Xử lý lỗi khôi phục bằng một đường phục hồi rõ ràng.
- Tránh lưu payload lớn hoặc tài nguyên sống trong flow scope.
- Kiểm thử hành vi khi lịch sử vượt giới hạn, session hết hạn hoặc execution bị loại bỏ.

## 1. Snapshot giúp khôi phục lịch sử như thế nào?

Một flow execution là một lần chạy cụ thể của flow definition. Trong quá trình chạy, người dùng đi qua các state, gửi event và tạo ra những phiên bản trạng thái khác nhau. Spring Web Flow có thể lưu snapshot của execution để một request sau đó tham chiếu đến đúng phiên bản trạng thái đã được tạo trước đó.

URL thực thi thường chứa một execution key. Ví dụ minh họa:

~~~text
/checkout?execution=e1s4
~~~

Trong dạng key thường gặp, phần `e1` xác định flow execution và phần `s4` xác định snapshot của execution đó. Khi người dùng chuyển từ một màn hình sang màn hình tiếp theo, flow xử lý event và tạo trạng thái có thể được lưu thành snapshot mới. URL mới trỏ đến snapshot mới này.

Nếu trình duyệt quay lại URL cũ, Spring Web Flow dùng execution key để tìm execution và snapshot tương ứng trong repository. Nếu snapshot vẫn còn, trạng thái đó có thể được khôi phục. Nếu snapshot đã bị loại bỏ, URL vẫn tồn tại trong lịch sử trình duyệt nhưng repository không thể dựng lại trạng thái chỉ từ URL.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant W as Spring Web Flow
    participant R as FlowExecutionRepository

    U->>B: Mở /checkout
    B->>W: Khởi chạy flow
    W->>R: Lưu snapshot s1
    R-->>W: execution e1, snapshot s1
    W-->>B: URL execution=e1s1

    U->>B: Gửi event continue
    B->>W: Request execution=e1s1
    W->>R: Khôi phục s1 và xử lý event
    W->>R: Lưu snapshot s2
    W-->>B: URL execution=e1s2

    Note over R: Khi vượt giới hạn, snapshot cũ bị loại bỏ

    U->>B: Nhấn Back đến URL e1s1
    B->>W: Request execution=e1s1
    W->>R: Tìm snapshot s1
    R-->>W: Không còn snapshot
    W-->>B: Lỗi khôi phục execution
~~~

Điểm cần nhớ: lịch sử trình duyệt lưu các URL mà trình duyệt đã truy cập; repository của Spring Web Flow lưu trạng thái execution mà các URL đó tham chiếu đến. Hai nơi có vòng đời riêng. Giữ một URL trong browser history không đảm bảo snapshot phía máy chủ còn tồn tại.

## 2. Vì sao snapshot cũ bị loại bỏ?

Repository thường giới hạn số snapshot được giữ cho mỗi flow execution. Giới hạn này giúp kiểm soát dung lượng session hoặc nơi lưu execution. Nếu một flow có nhiều bước, người dùng tiến qua nhiều state và tạo nhiều snapshot, repository sẽ phải loại bỏ snapshot cũ khi vượt giới hạn đã đặt.

Ví dụ, một execution chỉ giữ tối đa ba snapshot:

| Thời điểm | Snapshot mới | Snapshot còn được giữ |
|---|---|---|
| Flow bắt đầu | `s1` | `s1` |
| Người dùng tiếp tục | `s2` | `s1, s2` |
| Người dùng tiếp tục | `s3` | `s1, s2, s3` |
| Người dùng tiếp tục | `s4` | `s2, s3, s4` |
| Người dùng tiếp tục | `s5` | `s3, s4, s5` |

Khi `s4` được tạo, snapshot cũ nhất `s1` bị loại bỏ để repository giữ đúng ba snapshot. Nếu người dùng nhấn Back đến URL `execution=e1s1`, repository không còn snapshot `s1` để khôi phục.

Đây là hành vi quản lý tài nguyên có chủ đích. Giới hạn thấp giúp giảm lượng trạng thái phải lưu, nhưng cũng rút ngắn số bước lịch sử có thể quay lại. Giới hạn cao cho phép quay lại sâu hơn, đổi lại mỗi execution có thể chiếm nhiều dung lượng hơn.

## 3. Cấu hình max-execution-snapshots

Với cấu hình XML của Spring Web Flow, giới hạn snapshot được đặt trong phần tử `flow-execution-repository` bên trong `flow-executor`:

~~~xml
<flow:flow-executor id="flowExecutor"
                    flow-registry="flowRegistry">
    <flow:flow-execution-repository
            max-executions="5"
            max-execution-snapshots="40"/>
</flow:flow-executor>
~~~

Trong ví dụ:

- `max-execution-snapshots="40"` giới hạn số snapshot được giữ cho mỗi flow execution.
- `max-executions="5"` giới hạn số flow execution được giữ trong session theo cấu hình repository.

Hai thuộc tính kiểm soát hai cấp khác nhau. `max-execution-snapshots` giới hạn độ sâu lịch sử trong một execution. `max-executions` giới hạn số execution mà session có thể giữ, chẳng hạn khi người dùng mở nhiều quy trình độc lập trong cùng phiên đăng nhập.

Nếu cần cho phép người dùng quay lại nhiều bước hơn, hãy tăng `max-execution-snapshots` sau khi ước lượng dung lượng trạng thái. Không nên đặt một giá trị rất lớn chỉ để tránh lỗi Back. Mỗi snapshot có thể chứa flow state, dữ liệu trong scope và thông tin cần thiết để khôi phục execution. Flow scope càng lớn thì chi phí lưu từng snapshot càng cao.

Giá trị trong ví dụ chỉ là cấu hình minh họa, không phải mức phù hợp cho mọi ứng dụng. Hãy chọn giới hạn dựa trên số bước người dùng thực sự cần quay lại, kích thước dữ liệu trong flow, số execution đồng thời và cơ chế lưu repository đang dùng. Nếu ứng dụng dùng repository tùy biến, hãy kiểm tra thuộc tính tương đương của implementation đó; cấu hình XML mẫu áp dụng cho flow execution repository được cấu hình qua namespace Spring Web Flow.

## 4. Phân biệt các loại giới hạn và nguyên nhân mất lịch sử

Không phải mọi URL execution không khôi phục được đều do vượt giới hạn snapshot. Hãy phân biệt các trường hợp sau:

| Tình huống | Điều bị mất hoặc bị giới hạn | Biểu hiện thường gặp |
|---|---|---|
| Vượt `max-execution-snapshots` | Snapshot cũ trong một execution | URL cũ vẫn trỏ đến execution nhưng snapshot key không còn được repository giữ. |
| Vượt `max-executions` | Một execution cũ trong session | Người dùng quay lại URL thuộc execution đã bị loại bỏ khỏi repository. |
| HTTP session hết hạn | Repository gắn với session và các execution trong đó | Các URL cũ không còn tìm thấy execution tương ứng. |
| Ứng dụng khởi động lại với repository lưu trong bộ nhớ session | Trạng thái session/execution không được khôi phục | Các tab đang mở có thể trỏ đến execution không còn tồn tại. |
| Người dùng mở URL trong một session khác | Cookie/session không khớp với execution key | Repository của session hiện tại không tìm thấy execution. |
| Flow đã kết thúc | Execution không còn là flow đang hoạt động | Request cũ không thể tiếp tục quy trình đã hoàn tất. |

Lỗi do snapshot cũ bị loại bỏ khác với lỗi do execution không còn tồn tại. Khi chẩn đoán, hãy xem execution key, session hiện tại, trạng thái repository và thời điểm flow kết thúc. Không nên tăng giới hạn snapshot nếu nguyên nhân thật sự là session hết hạn hoặc execution bị loại bỏ bởi giới hạn `max-executions`.

Ngoài ra, trình duyệt có thể hiển thị lại trang từ cache khi người dùng nhấn Back. Nội dung HTML xuất hiện không chứng minh rằng snapshot vẫn còn. Khi người dùng thao tác tiếp hoặc trình duyệt gửi request, máy chủ mới cần khôi phục execution. Vì vậy, kiểm tra phải dựa trên request và response thực tế, không chỉ quan sát màn hình được cache.

## 5. Thiết kế dữ liệu để snapshot gọn nhẹ

Một snapshot có thể chứa dữ liệu trong flow scope và trạng thái của flow tại thời điểm lưu. Nếu ứng dụng đặt toàn bộ nội dung biểu mẫu lớn, file upload, mảng byte hoặc đối tượng phụ thuộc request vào scope, mỗi snapshot sẽ tốn thêm dung lượng.

Nên giữ trong flow những dữ liệu cần để tiếp tục quy trình:

- Mã định danh hồ sơ hoặc giao dịch.
- Các lựa chọn người dùng cần dùng ở state tiếp theo.
- Trạng thái nghiệp vụ ngắn gọn.
- Metadata và tham chiếu đến tài liệu lưu ở hệ thống bên ngoài.

Nên lưu dữ liệu lớn hoặc dữ liệu dài hạn trong tầng lưu trữ nghiệp vụ, rồi giữ khóa tham chiếu trong flow:

~~~java
public class CheckoutState {

    private String orderId;
    private String customerId;
    private String selectedDeliveryOption;
    private String draftReference;

    // Getters và setters
}
~~~

Ví dụ này cho thấy flow có thể giữ mã đơn hàng, mã khách hàng, lựa chọn giao hàng và tham chiếu bản nháp. Nội dung tệp đính kèm hoặc toàn bộ dữ liệu đơn hàng có thể được lưu trong dịch vụ nghiệp vụ. Khi khôi phục flow, action tải dữ liệu cần thiết theo mã tham chiếu.

Không nên giữ các đối tượng có vòng đời gắn với một request hoặc tài nguyên đang mở như `HttpServletRequest`, `InputStream`, kết nối JDBC hoặc `EntityManager`. Chúng không phù hợp với trạng thái có thể được lưu rồi khôi phục ở một request khác. Với repository cần serialization, các đối tượng trong scope còn phải tương thích với cơ chế serialization của implementation.

Snapshot gọn nhẹ giúp giảm chi phí khi giữ nhiều bước lịch sử, đồng thời giảm rủi ro lỗi khi session được lưu hoặc khôi phục. Tối ưu kích thước dữ liệu trong flow thường hữu ích hơn việc chỉ tăng giới hạn snapshot.

## 6. Xử lý khi trình duyệt quay lại snapshot đã mất

Khi request tham chiếu đến snapshot không còn tồn tại, ứng dụng không thể tái tạo trạng thái cũ chỉ từ execution key. Cần xử lý lỗi khôi phục ở tầng điều phối request hoặc flow handler để đưa người dùng đến một trang phục hồi dễ hiểu.

Một trang phục hồi nên giải thích rằng bước trước không còn khả dụng và cung cấp đường đi an toàn, ví dụ:

- Quay về trang danh sách hồ sơ hoặc dashboard.
- Mở một flow mới nếu nghiệp vụ cho phép bắt đầu lại.
- Tải lại dữ liệu đã lưu từ hệ thống nghiệp vụ bằng mã hồ sơ, nếu người dùng có quyền.
- Liên hệ hỗ trợ nếu quy trình đã tạo giao dịch nhưng trạng thái hiển thị chưa rõ.

Không nên tự động coi request có execution key cũ là một flow mới. Một request cũ có thể là POST mang event hoặc dữ liệu đã gửi trước đó. Tự khởi chạy flow mới từ request này có thể làm sai ý định người dùng hoặc lặp thao tác nghiệp vụ.

Với các thao tác có side effect như thanh toán, đặt chỗ hoặc tạo hồ sơ, hãy bảo đảm dịch vụ nghiệp vụ có tính lặp an toàn. Khi người dùng quay lại một snapshot cũ, không được giả định rằng thao tác đã commit trước đó sẽ tự động được hoàn tác. Flow snapshot phản ánh trạng thái điều phối, còn giao dịch nghiệp vụ có vòng đời riêng trong cơ sở dữ liệu hoặc hệ thống ngoài.

Có thể tổ chức đường phục hồi ở mức khái niệm như sau:

~~~mermaid
flowchart TD
    A[Request mang execution key cũ] --> B[Repository tìm execution và snapshot]
    B --> C{Snapshot còn tồn tại?}
    C -->|Có| D[Khôi phục flow và xử lý request]
    C -->|Không| E[Phân loại lỗi khôi phục]
    E --> F{Execution còn tồn tại?}
    F -->|Có| G[Snapshot đã bị loại bỏ]
    F -->|Không| H[Execution hoặc session đã hết hạn]
    G --> I[Hiển thị trang phục hồi]
    H --> I
    I --> J[Trang danh sách hoặc khởi chạy flow mới có chủ đích]
~~~

Tùy phiên bản và cách tích hợp, lỗi khôi phục có thể được thể hiện bằng exception thuộc nhóm `FlowExecutionRestorationFailureException`. Hãy xử lý exception tại đúng ranh giới web/flow handler của ứng dụng và tránh để stack trace hoặc execution key nội bộ xuất hiện với người dùng. Khi triển khai, kiểm tra exception thực tế của phiên bản Spring Web Flow đang dùng và ánh xạ nó sang trang lỗi phù hợp.

## 7. Chọn giới hạn snapshot theo hành vi người dùng

Không có một con số duy nhất phù hợp cho mọi flow. Hãy bắt đầu từ hành vi người dùng:

| Đặc điểm quy trình | Cách chọn giới hạn |
|---|---|
| Biểu mẫu ngắn, 3–5 bước, dữ liệu nhỏ | Giới hạn vừa phải có thể đáp ứng lịch sử quay lại thông thường. |
| Quy trình dài, nhiều bước rà soát và sửa dữ liệu | Cân nhắc tăng số snapshot để hỗ trợ quay lại sâu hơn. |
| Flow giữ nhiều metadata hoặc nhiều nhánh lồng nhau | Đo kích thước snapshot và tối ưu dữ liệu trước khi tăng giới hạn. |
| Nhiều flow execution đồng thời trong một session | Cân nhắc đồng thời `max-executions` và `max-execution-snapshots`. |
| Flow có thao tác nghiệp vụ không thể đảo ngược | Thiết kế xác nhận, idempotency và phục hồi nghiệp vụ; không dựa vào lịch sử trình duyệt để hoàn tác. |

Nên theo dõi số snapshot được giữ, kích thước trạng thái, số lần lỗi khôi phục và số lần người dùng phải bắt đầu lại. Nếu repository dùng session phía máy chủ, hãy theo dõi mức sử dụng bộ nhớ session và số session đồng thời. Nếu dùng repository khác, theo dõi dung lượng và thời gian truy xuất snapshot của implementation đó.

Tăng giới hạn snapshot có thể cải thiện trải nghiệm Back/Forward nhưng cũng làm tăng chi phí lưu trữ. Hãy thử với tải đại diện và số bước tương tự quy trình thực tế trước khi áp dụng cấu hình rộng cho toàn hệ thống.

## 8. Kiểm thử khi snapshot vượt giới hạn

Một bài kiểm thử tích hợp có thể cấu hình giới hạn nhỏ, ví dụ ba snapshot cho mỗi execution, để tái hiện lỗi một cách nhanh chóng:

1. Khởi chạy flow và lưu URL execution đầu tiên.
2. Gửi các event để flow đi qua nhiều state hơn giới hạn.
3. Giữ lại các URL execution mà trình duyệt đã nhận trong từng bước.
4. Dùng cùng session/cookie để gửi request đến URL snapshot cũ nhất.
5. Xác nhận repository không còn snapshot đó và ứng dụng hiển thị đường phục hồi.
6. Gửi request đến URL của snapshot gần nhất còn được giữ và xác nhận flow có thể khôi phục.
7. Khởi chạy flow thứ hai để kiểm tra riêng giới hạn số execution.
8. Lặp lại với session hết hạn để phân biệt lỗi session với lỗi snapshot.

Ma trận kiểm thử:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Quay lại snapshot vẫn còn trong giới hạn | Flow khôi phục đúng state và dữ liệu tại snapshot đó. |
| Quay lại snapshot cũ đã bị loại bỏ | Lỗi khôi phục được xử lý; người dùng nhận trang phục hồi. |
| Tiếp tục từ snapshot mới nhất | Flow tiếp tục bình thường và tạo snapshot mới. |
| Vượt giới hạn số execution | Execution cũ bị loại bỏ theo chính sách repository; không nhầm với snapshot cũ trong execution còn tồn tại. |
| Session hết hạn | Trang phục hồi thông báo phiên hoặc quy trình đã hết hạn. |
| Người dùng gửi lại thao tác xác nhận | Dịch vụ nghiệp vụ không tạo giao dịch trùng. |
| Snapshot chứa dữ liệu lớn | Đo được kích thước và chi phí lưu; không lưu payload không cần thiết. |
| Browser hiển thị trang cache | Request thực tế vẫn được máy chủ kiểm tra và xử lý đúng khi người dùng thao tác tiếp. |

Trong kiểm thử, hãy ghi lại execution key và state mong đợi của từng bước. Không dùng một session mới cho request quay lại, vì điều đó chỉ kiểm tra lỗi không tìm thấy execution trong session khác chứ không kiểm tra snapshot bị loại bỏ do vượt giới hạn.

## 9. Nguyên tắc vận hành lâu dài

Snapshot giúp Spring Web Flow khôi phục các phiên bản trạng thái phục vụ lịch sử trình duyệt, nhưng số snapshot được giữ có giới hạn. Khi giới hạn bị vượt, URL cũ có thể vẫn nằm trong browser history nhưng không còn trạng thái tương ứng ở repository.

Hãy cấu hình `max-execution-snapshots` theo độ sâu quay lại thực tế và theo dõi chi phí lưu trạng thái. Phân biệt nó với `max-executions`, session timeout và việc flow kết thúc. Giữ flow scope gọn nhẹ bằng mã định danh, metadata và tham chiếu đến dữ liệu nghiệp vụ. Khi snapshot không còn, hiển thị đường phục hồi rõ ràng và bảo đảm thao tác nghiệp vụ không bị thực hiện lặp.

Cách thiết kế này giúp lịch sử trình duyệt có hành vi dự đoán được, flow execution không chiếm quá nhiều tài nguyên và người dùng vẫn có hướng tiếp tục khi một bước lịch sử đã hết thời gian lưu giữ.
