# Nhân bản tab và dùng lại cùng execution key

Trong một ứng dụng **Spring Web Flow (SWF)**, URL của một màn hình đang chạy thường chứa thông tin để tiếp tục flow execution hiện tại. Khi người dùng **nhân bản tab trình duyệt (Duplicate tab)**, trình duyệt sao chép URL và cookie phiên sang tab mới. Nếu URL đang chứa execution key, hai tab có thể cùng tham chiếu **một flow execution và một snapshot**. Người dùng tưởng rằng họ đã mở hai hành trình độc lập, nhưng thực tế họ đang thao tác trên cùng ngữ cảnh phía server.

Tình huống này dễ gây lỗi ở flow nhiều bước: tab A chọn dịch vụ X, tab B chọn dịch vụ Y; tab A xác nhận trước, rồi tab B gửi tiếp một event từ URL cũ. Kết quả phụ thuộc snapshot còn được lưu hay không, repository xử lý request đồng thời ra sao và service nghiệp vụ bảo vệ giao dịch thế nào. Nếu không thiết kế rõ, người dùng có thể thấy dữ liệu thay đổi bất ngờ, gặp execution hết hạn hoặc gửi một thao tác ghi nhiều lần.

Bài thuộc chương **Lịch sử trình duyệt** của module `SPRING_WEB_FLOW`. Nội dung tập trung vào quan hệ giữa **tab, HTTP session, flow execution key và execution snapshot**, cách nhận biết một tab mới đang dùng lại execution cũ, cách tạo flow execution độc lập, và cách bảo vệ các thao tác không thể lặp. Ví dụ dùng Spring Web Flow với Spring MVC; các chi tiết repository và URL cần được xác minh trên đúng phiên bản/cấu hình của ứng dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao Duplicate tab có thể sao chép **execution URL/key**, chứ không tự tạo flow execution mới.
2. Phân biệt browser tab, HTTP session, flow execution, flow conversation và snapshot.
3. Mô tả điều gì có thể xảy ra khi hai tab gửi event từ cùng một execution key.
4. Phân biệt URL bắt đầu flow với URL tiếp tục flow.
5. Thiết kế liên kết “Bắt đầu hành trình mới” để tạo execution độc lập.
6. Hiểu tác động của browser Back, refresh, submit lặp và snapshot retention.
7. Bảo vệ thao tác ghi bằng idempotency, transaction, unique constraint và kiểm tra phiên bản dữ liệu.
8. Viết kịch bản kiểm thử cho hai tab, request đồng thời, key cũ và session hết hạn.

Kết quả cần đạt không phải là cấm người dùng mở nhiều tab. Ứng dụng phải **nói rõ tab nào đang tiếp tục hành trình nào**, cho phép tạo hành trình mới có chủ đích và bảo vệ nghiệp vụ khi request cũ được gửi lại.

## 2. Bốn khái niệm cần tách biệt

| Khái niệm | Là gì? | Có được chia sẻ giữa hai tab? |
| --- | --- | --- |
| **Browser tab** | Một trang đang mở trong trình duyệt, có URL và lịch sử điều hướng riêng | Mỗi tab là một giao diện riêng |
| **HTTP session** | Phiên server được trình duyệt tham chiếu bằng cookie/session identifier | Thường được các tab cùng origin chia sẻ |
| **Flow execution** | Một lần chạy flow, gồm state và dữ liệu của hành trình | Có thể được nhiều tab tham chiếu nếu URL key bị sao chép |
| **Execution snapshot/continuation** | Trạng thái được lưu để tiếp tục hoặc quay lại theo cơ chế repository | Có thể được URL của nhiều tab tham chiếu |

Điểm quan trọng: **hai tab không đồng nghĩa hai session, và hai URL giống nhau không đồng nghĩa hai execution độc lập**. Trình duyệt thường gửi cùng cookie session cho các tab cùng website. Nếu URL cũng chứa cùng execution key, hai tab có thể truy cập cùng flow execution.

### 2.1. Execution key nhận diện điều gì?

Web Flow dùng một khóa thực thi để xác định flow execution cần tiếp tục. Trong mô hình repository dựa trên snapshot, khóa thường mang thông tin nhận diện execution và snapshot/continuation tương ứng. Tên và định dạng chuỗi cụ thể là chi tiết triển khai; ví dụ thường thấy có dạng:

~~~text
/booking?execution=e1s4
~~~

`e1s4` chỉ là **ví dụ minh họa**, không phải định dạng mà ứng dụng nên tự tạo hoặc phân tích. Hãy dùng URL do Web Flow cung cấp, thường qua biến `flowExecutionUrl` trong view.

Execution key:

- Giúp Web Flow tìm đúng execution/snapshot để xử lý request tiếp theo.
- Không phải mã định danh người dùng, mã booking hay token xác thực.
- Không tự chứng minh người đang gửi request có quyền xem hoặc sửa dữ liệu nghiệp vụ.
- Có thể hết hiệu lực khi execution/snapshot bị loại bỏ, kết thúc hoặc session/repository không còn dữ liệu.

### 2.2. Sơ đồ hai tab cùng trỏ tới một execution

~~~mermaid
flowchart TD
    S["HTTP session của trình duyệt"] --> A["Tab A"]
    S --> B["Tab B: Duplicate tab"]
    A --> U["URL chứa execution key K"]
    B --> U
    U --> R["Flow execution repository"]
    R --> E["Cùng execution / snapshot được tham chiếu"]
~~~

Tab A và tab B có lịch sử trình duyệt riêng, nhưng URL ban đầu có thể trỏ tới cùng execution key. **Lịch sử ở phía client và trạng thái flow ở phía server là hai thứ khác nhau.**

## 3. URL bắt đầu flow và URL tiếp tục flow

Đây là phân biệt quan trọng nhất để xử lý tab:

| Loại URL | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Flow start URL** | `/booking` | Gửi request tới flow handler để bắt đầu một execution mới, theo cấu hình mapping |
| **Flow continuation URL** | `/booking?execution=...` | Tiếp tục execution/snapshot đã tồn tại |
| **Business resource URL** | `/reservations/RSV-1001` | Đọc một booking đã lưu từ database, có authorization riêng |

Trong Spring MVC integration, `FlowHandlerMapping` ánh xạ URL tới flow ID, còn `FlowHandlerAdapter` chuyển request vào `FlowExecutor`. Một request tới URL bắt đầu flow không mang execution key thường tạo execution mới; request tới URL do `flowExecutionUrl` cung cấp tiếp tục execution đang chạy.

~~~mermaid
flowchart TD
    A["GET /booking"] --> B["FlowHandlerMapping tìm flow booking"]
    B --> C["FlowExecutor bắt đầu execution mới"]
    C --> D["Render view-state đầu"]
    D --> E["flowExecutionUrl có execution key"]
    E --> F["POST event next/confirm"]
    F --> G["Tiếp tục execution hiện tại"]
~~~

**Không tự xóa tham số execution khỏi URL đang chạy để tạo flow mới.** Hãy dùng URL bắt đầu flow do ứng dụng định nghĩa, ví dụ `/booking`, hoặc một link rõ nghĩa tới endpoint mở hành trình mới. Không sửa chuỗi execution key bằng JavaScript.

## 4. Điều gì xảy ra khi Duplicate tab?

Giả sử người dùng đang ở màn hình `review` của flow đặt chỗ:

~~~text
Tab A:
  /booking?execution=K
  draft.serviceId = 101
  state = review

Duplicate tab

Tab B:
  /booking?execution=K
  draft.serviceId = 101
  state ban đầu được tham chiếu = review
~~~

Khi nhân bản tab, trình duyệt thường sao chép **URL hiện tại** và tiếp tục gửi cookie session. Nó không yêu cầu Web Flow tạo một flow execution mới. Vì vậy hai tab có thể cùng đọc và gửi request dựa trên cùng trạng thái đã lưu.

### 4.1. Hai tab không có bản sao dữ liệu độc lập chỉ vì giao diện được nhân đôi

Khi người dùng sửa một input trong tab A nhưng chưa submit, thay đổi đó chỉ ở DOM của tab A. Tab B không tự nhìn thấy nội dung chưa gửi. Tuy nhiên, khi tab A submit, dữ liệu được bind vào execution phía server và tạo ra trạng thái tiếp theo. Tab B vẫn giữ URL/key cũ, nhưng khi gửi request, server sẽ xử lý theo semantics của repository và snapshot được key đó tham chiếu.

Do đó có hai lớp trạng thái:

- **Client state:** input chưa gửi, scroll, form controls, history của mỗi tab.
- **Server flow state:** object trong scope, state hiện tại/snapshot, message context và các dữ liệu flow đã nhận.

Đừng giả định client state của tab này tự đồng bộ sang tab kia; cũng đừng giả định server state được nhân đôi theo mỗi tab.

### 4.2. Ví dụ xung đột hai tab

~~~mermaid
sequenceDiagram
    participant A as Tab A
    participant B as Tab B
    participant R as Flow repository
    A->>R: POST event next với key K
    R-->>A: Xử lý snapshot K, trả view/key tiếp theo K1
    Note over B: Tab B vẫn giữ URL key K
    B->>R: POST event confirm với key K
    R-->>B: Kết quả phụ thuộc snapshot K còn hợp lệ và repository policy
~~~

Sau khi tab A chuyển state, tab B vẫn không tự đổi URL thành key mới của A. Khi B gửi request cũ, các khả năng có thể gồm:

1. Repository vẫn giữ snapshot cũ và cho phép khôi phục; B tiếp tục từ trạng thái lịch sử đó.
2. Snapshot đã bị loại bỏ hoặc execution đã kết thúc; B nhận lỗi execution/snapshot không còn tồn tại.
3. Request bị từ chối vì event không hợp lệ ở trạng thái được phục hồi hoặc vì kiểm soát đồng thời.
4. Hệ thống khôi phục một continuation cũ và tạo ra một nhánh lịch sử khác theo cơ chế snapshot.

**Không nên khẳng định một kết quả duy nhất cho mọi ứng dụng.** Hành vi chính xác phụ thuộc loại `FlowExecutionRepository`, snapshot policy, lock/concurrency handling, cấu hình history và version Web Flow. Hãy kiểm thử với repository thực tế mà production sử dụng.

## 5. Execution snapshot, continuation và browser history

Web Flow hỗ trợ tiếp tục flow qua nhiều request và có cơ chế lưu trạng thái thực thi để phục vụ history/back. Trong repository snapshot-based, một URL có thể trỏ tới snapshot cụ thể của execution. Khi flow chuyển state, URL continuation mới được phát ra cho trạng thái tiếp theo.

Một cách hình dung:

~~~mermaid
flowchart LR
    K0["Key K0<br/>enterDetails"] --> K1["Key K1<br/>chooseService"]
    K1 --> K2["Key K2<br/>review"]
    K2 --> K3["Key K3<br/>completed"]
    K2 -. "Browser Back / continuation cũ" .-> K1
~~~

Sơ đồ thể hiện quan hệ lịch sử ở mức khái niệm; không phải cam kết mỗi transition luôn tạo một chuỗi key theo đúng ký hiệu hoặc mọi snapshot đều được giữ mãi. Repository có giới hạn số execution/snapshot và có thể dọn lịch sử cũ.

### 5.1. Snapshot giúp gì?

- Cho phép flow tiếp tục qua request HTTP mới.
- Hỗ trợ quay lại trạng thái trước trong phạm vi history được lưu.
- Giữ dữ liệu flow theo execution thay vì phải gửi lại toàn bộ dữ liệu qua query string.
- Cho phép Web Flow khôi phục trạng thái tương ứng khi nhận continuation key hợp lệ.

### 5.2. Snapshot không bảo đảm điều gì?

- Không tạo một execution độc lập cho mỗi tab được nhân bản.
- Không đồng bộ URL/key giữa các tab.
- Không khóa nghiệp vụ hoặc bảo đảm không có hai request xác nhận cùng lúc.
- Không bảo đảm mọi key cũ còn dùng được vô thời hạn.
- Không thay thế authorization, validation, idempotency hay transaction của service.

### 5.3. Giới hạn history

Flow executor/repository có thể giới hạn số execution và số snapshot được lưu. Khi giới hạn bị vượt, snapshot cũ có thể bị loại bỏ. Cấu hình thường gặp trong XML namespace là phần `flow-execution-repository` với các thuộc tính giới hạn execution/snapshot; tên bean/API cụ thể cần đối chiếu version.

Ví dụ cấu hình minh họa:

~~~xml
<webflow:flow-executor id="flowExecutor"
                       flow-registry="flowRegistry">
    <webflow:flow-execution-repository
        max-executions="5"
        max-execution-snapshots="30"/>
</webflow:flow-executor>
~~~

Đoạn XML trên cần được xác minh với schema và cấu hình hiện hành của dự án; các giá trị `5` và `30` chỉ là ví dụ, không phải khuyến nghị mặc định. Tăng snapshot limit có thể làm session/repository tốn bộ nhớ hơn, nhất là khi flowScope giữ object lớn.

## 6. Tạo flow execution độc lập cho tab mới

Nếu người dùng muốn mở **một hành trình mới**, ứng dụng phải đưa họ tới **flow start URL**, không phải continuation URL của execution hiện tại.

Ví dụ khi flow ID `booking` được ánh xạ vào `/booking`:

~~~html
<!-- Tiếp tục flow đang mở: dùng execution URL do Web Flow cung cấp -->
<form method="post" th:action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>

<!-- Bắt đầu một flow execution mới -->
<a th:href="@{/booking}" target="_blank" rel="noopener">
    Mở một lượt đặt chỗ mới
</a>
~~~

Link thứ hai trỏ tới URL bắt đầu flow, không mang execution key. Khi người dùng mở link, FlowHandlerMapping tìm flow ID và FlowExecutor bắt đầu execution mới theo cấu hình ứng dụng. Hai execution có thể vẫn nằm trong **cùng HTTP session**, nhưng mỗi execution có bản nháp và lịch sử riêng.

### 6.1. So sánh hai cách mở tab

| Thao tác | URL được sao chép/mở | Kết quả dự kiến |
| --- | --- | --- |
| Duplicate tab từ màn hình đang chạy | Continuation URL có key | Tab mới tham chiếu execution/snapshot hiện tại |
| Ctrl+L rồi dán URL hiện tại | Continuation URL có key | Vẫn tham chiếu execution/snapshot đó |
| Mở link `/booking` | Start URL không có key | Tạo execution mới theo flow mapping |
| Nhấn “Mở lượt mới” có `target="_blank"` | Start URL trong tab mới | Execution mới, cùng session nếu cookie được gửi |
| Dùng URL biên lai `/reservations/123` | Business resource URL | Đọc bản ghi đã lưu, không khởi tạo flow mới |

### 6.2. Nên đặt liên kết “Mở hành trình mới” ở đâu?

- Ở trang hoàn tất, để người dùng bắt đầu một booking khác.
- Ở dashboard hoặc trang danh sách, nơi người dùng chủ động tạo giao dịch mới.
- Ở trang lỗi execution hết hạn, để khởi tạo lại một hành trình sạch.
- Trong một tab riêng nếu sản phẩm cho phép làm nhiều việc song song.

Không đặt link “Mở hành trình mới” trỏ về `flowExecutionUrl`; như vậy chỉ tiếp tục execution cũ. Nếu cần điều hướng trong cùng tab, link start URL vẫn tạo execution mới nhưng người dùng có thể rời khỏi view cũ. Hãy cân nhắc có lưu nháp/đường quay lại hay không.

### 6.3. Có nên tự động phát hiện tab bị nhân bản?

Trình duyệt không gửi một định danh “tab này là bản sao” chuẩn hóa trong HTTP request. Server thường chỉ thấy cookie, URL, header và body. Một request có execution key cũ cũng có thể đến từ:

- Tab được nhân bản.
- Bookmark hoặc link người dùng lưu lại.
- Browser Back/Forward.
- Refresh hoặc retry.
- Một request được gửi lại sau lỗi mạng.

Do đó, **không nên dựa vào suy đoán Duplicate tab để quyết định quyền hoặc tính hợp lệ của giao dịch**. Thiết kế flow và service phải chịu được request lặp/cũ theo chính sách.

Nếu sản phẩm thật sự cần giới hạn một execution đang hoạt động trên mỗi người dùng, hãy mô hình hóa quy tắc đó ở server bằng trạng thái nghiệp vụ, thời hạn và cơ chế khóa/lease rõ ràng. Không dùng JavaScript tab ID như cơ chế bảo mật; người dùng có thể sửa hoặc bỏ nó.

## 7. Kịch bản hai tab dùng cùng execution key

Giả sử flow đặt dịch vụ có state:

~~~mermaid
stateDiagram-v2
    [*] --> search
    search --> choose: find
    choose --> review: next
    review --> completed: confirm
    completed --> [*]
~~~

Người dùng tìm thấy dịch vụ A, đi tới `review`, sau đó nhân bản tab:

| Thời điểm | Tab A | Tab B |
| --- | --- | --- |
| Ban đầu | URL key K, state `review`, chọn A | Chưa mở |
| Duplicate | Vẫn ở K | Cũng mở URL K, state được tham chiếu là `review` |
| A bấm Confirm | Gửi event `confirm` với K | Vẫn giữ URL K |
| A nhận kết quả | Có thể được chuyển tới key mới hoặc end-state | Không tự nhận URL mới từ A |
| B bấm Back/Confirm | Không ảnh hưởng trực tiếp tới DOM tab A | Gửi request dựa trên key/snapshot cũ |

Tab B không có “bản sao độc lập” của flow chỉ vì có DOM riêng. Cả hai request cùng trỏ vào execution history có liên hệ. Nếu snapshot K còn được giữ, B có thể khôi phục trạng thái cũ; nếu không, B có thể nhận lỗi expired execution. Nếu request A và B chạy đồng thời, cơ chế lock/repository có thể tuần tự hóa hoặc từ chối một request; cần xác minh theo cấu hình.

### 7.1. Hai người dùng khác nhau không giống hai tab

Hai tab cùng trình duyệt thường chia sẻ session cookie; hai người dùng với session khác nhau thường có execution repository/context khác nhau. Tuy nhiên:

- Cùng execution key nhưng **session khác** không có nghĩa người dùng thứ hai được phép truy cập execution của người thứ nhất.
- Nếu repository được lưu server-side trong session, key không tìm được execution trong session mới.
- Nếu dùng repository tùy chỉnh hoặc lưu trữ phân tán, phải đảm bảo key được ràng buộc với đúng conversation/session và principal.
- Mọi truy cập dữ liệu nghiệp vụ vẫn cần authorization tại service.

Không coi execution key là secret bearer token có thể thay thế đăng nhập. Nó là một phần định tuyến/khôi phục flow, không phải chính sách truy cập.

### 7.2. Bản nháp có thể rẽ nhánh không?

Với continuation/snapshot repository, một request từ key cũ có thể khôi phục snapshot cũ nếu snapshot còn hiệu lực. Từ góc nhìn người dùng, điều này có thể trông như hai nhánh cùng bắt đầu từ một điểm. Nhưng **không nên thiết kế nghiệp vụ dựa vào giả định rằng mọi repository sẽ cho phép fork**, hoặc mọi fork được cách ly hoàn toàn.

Hãy xem các snapshot là cơ chế điều hướng/history của Web Flow, không phải phiên bản độc lập của một giao dịch nghiệp vụ. Nếu cần tạo hai booking khác nhau, hãy mở hai execution mới từ start URL để mỗi bản nháp có identity riêng.

## 8. Browser Back, Forward, refresh và submit lặp

Các thao tác trình duyệt thường gặp không có cùng semantics:

| Thao tác | Phía trình duyệt | Phía Web Flow cần lưu ý |
| --- | --- | --- |
| Nút Back trong form | Gửi event `back` nếu form có nút riêng | Chạy transition được định nghĩa |
| Browser Back | Đi tới URL/snapshot trước trong history | Có thể khôi phục snapshot cũ hoặc gặp expired key |
| Browser Forward | Mở lại URL tiếp theo trong history nếu còn | Snapshot có thể còn hoặc đã bị dọn |
| Refresh view GET | Gửi lại GET URL hiện tại | Có thể render lại snapshot/execution tương ứng |
| Refresh trang POST | Trình duyệt có thể hỏi resubmit | PRG giảm việc gửi lại POST, nhưng không thay idempotency |
| Double-click submit | Có thể tạo hai request gần nhau | Repository và service phải xử lý concurrency/retry |
| Duplicate tab | Sao chép URL/cookie | Có thể dùng lại execution key và cùng session |

### 8.1. PRG giúp giảm nhưng không loại bỏ request lặp

Post/Redirect/Get chuyển trình duyệt từ POST sang GET sau khi flow pause tại một view-state. Điều này hữu ích cho thao tác refresh sau khi submit: người dùng thường tải lại trang GET thay vì gửi lại form POST.

Tuy vậy, PRG không bảo vệ trường hợp:

- Hai request POST cùng được gửi trước khi redirect hoàn tất.
- Tab khác gửi lại key cũ.
- Client retry vì không nhận được response.
- Người dùng mở cùng continuation URL trong một tab khác.
- Một action đã commit nhưng flow chưa kịp render kết quả.

Vì vậy thao tác có hiệu ứng phải được thiết kế idempotent hoặc có cơ chế chống trùng phù hợp.

### 8.2. History policy và transition không thể đảo ngược

Web Flow có hỗ trợ điều khiển history trên transition trong các phiên bản tương ứng. Với một thao tác nhạy cảm hoặc không nên quay lại để thực thi lại, có thể xem xét chính sách history như `invalidate` theo schema/version đang dùng. Nhưng đây chỉ là **quản lý history của flow**; nó không hoàn tác hoặc bảo vệ giao dịch đã ghi trong database.

Nếu người dùng quay lại snapshot cũ sau khi booking đã được xác nhận, service vẫn phải đọc trạng thái booking hiện tại và từ chối một lệnh xác nhận không còn hợp lệ. Không dựa vào việc xóa snapshot như lớp bảo vệ duy nhất.

## 9. Chống thực hiện nghiệp vụ hai lần

Execution key và idempotency key có hai mục đích khác nhau:

| Khóa | Dùng để | Không nên dùng để |
| --- | --- | --- |
| **Flow execution key** | Tiếp tục một flow execution/snapshot | Chống booking trùng hoặc xác thực người dùng |
| **Idempotency key** | Nhận diện một lệnh nghiệp vụ có thể được gửi lại | Điều hướng state/view |
| **Business ID** | Nhận diện booking đã được tạo | Xác định snapshot đang mở |
| **HTTP session ID** | Liên kết request vào session | Làm khóa duy nhất cho từng tab |

### 9.1. Tạo idempotency key phía server

Khi bắt đầu một hành trình đặt chỗ, server tạo một request ID ngẫu nhiên và giữ nó trong bản nháp của **execution đó**:

~~~java
public class BookingDraft implements java.io.Serializable {
    private final String requestId = java.util.UUID.randomUUID().toString();
    public String getRequestId() {
        return requestId;
    }
}
~~~

Nếu hai tab cùng dùng một execution, chúng có thể cùng tham chiếu bản nháp và request ID này. Khi gửi lệnh xác nhận lặp, service nhận diện đó là cùng một yêu cầu nghiệp vụ. Nếu người dùng mở flow mới qua start URL, draft mới có request ID mới, phù hợp với một booking mới.

**Không bind request ID từ form.** Nếu client tự thay ID, họ có thể phá cơ chế idempotency hoặc cố ý tạo nhiều yêu cầu. Request ID phải được tạo, lưu và xác minh ở server.

### 9.2. Ràng buộc duy nhất trong database

Một cách phổ biến là ràng buộc duy nhất theo người dùng và request ID:

~~~sql
ALTER TABLE reservation
ADD CONSTRAINT uq_reservation_user_request
UNIQUE (user_id, request_id);
~~~

Tên bảng/field cần điều chỉnh theo schema. Ràng buộc database là lớp cuối ngăn hai transaction đồng thời tạo hai bản ghi cho cùng một lệnh. Chỉ kiểm tra bằng câu `SELECT` trước khi `INSERT` không đủ vì hai transaction có thể cùng đọc “chưa tồn tại”.

### 9.3. Pseudocode của service

~~~java
@Transactional
public ConfirmationReceipt confirm(ConfirmCommand command) {
    String userId = currentPrincipal.requireUserId();

    // Nếu cùng yêu cầu đã commit, trả receipt cũ.
    var existing = reservationRepository
        .findByUserIdAndRequestId(userId, command.requestId());
    if (existing.isPresent()) {
        return existing.get().toReceipt();
    }

    // Kiểm tra quyền, trạng thái, giá và sức chứa ở thời điểm commit.
    var slot = slotRepository.findForUpdate(
        command.serviceId(), command.visitDate());
    validateCanReserve(userId, slot, command);

    // Tạo reservation với UNIQUE(user_id, request_id).
    return reservationRepository.save(
        createReservation(userId, slot, command)).toReceipt();
}
~~~

Đây là **pseudocode gần Java**, các repository, principal, exception và phương thức nghiệp vụ phải được ứng dụng cung cấp. Để xử lý hai request đồng thời cùng request ID, cần bắt xung đột unique trong ranh giới transaction phù hợp, rollback transaction thua rồi đọc lại receipt đã commit. Không tiếp tục dùng transaction đã bị đánh dấu rollback-only.

### 9.4. Side effect bên ngoài database

Nếu confirm gửi email, trừ tiền hoặc gọi nhà cung cấp bên ngoài, transaction database không tự làm các side effect đó exactly-once. Hãy dùng idempotency key của nhà cung cấp nếu có, transactional outbox hoặc quy trình bù trừ; không gửi email “thành công” trước khi biết transaction đã commit.

## 10. Request đồng thời và khóa flow execution

Hai tab có thể gửi request gần như cùng lúc. Cần tách hai loại đồng thời:

1. **Đồng thời ở tầng flow:** hai request cùng tiếp tục một execution/snapshot.
2. **Đồng thời ở tầng nghiệp vụ:** hai request cùng cố đặt một suất, cập nhật một hồ sơ hoặc thanh toán.

Flow repository có thể có cơ chế khóa execution để tránh hai request đồng thời sửa cùng một đối tượng flow trong bộ nhớ. Nhưng chi tiết lock, snapshot restoration và xử lý request đến sau phụ thuộc implementation/version. Ngay cả khi flow repository tuần tự hóa request, service/database vẫn phải bảo vệ bất biến nghiệp vụ vì:

- Có thể có nhiều execution khác nhau cùng đặt một slot.
- Có thể có một API/controller khác gọi cùng service.
- Request retry có thể tới sau khi execution đã thay đổi.
- Side effect bên ngoài không nằm trong khóa flow.

### 10.1. Minh họa hai request cùng key

~~~mermaid
sequenceDiagram
    participant A as Tab A
    participant B as Tab B
    participant Repo as Flow repository
    participant Service as Booking service
    participant DB as Database
    par Request A
        A->>Repo: POST confirm với key K
        Repo->>Service: Xử lý event/action
        Service->>DB: Transaction xác nhận
        DB-->>Service: Commit
        Service-->>Repo: Receipt
        Repo-->>A: Response/key tiếp theo
    and Request B
        B->>Repo: POST confirm với key K
        Note over Repo: Có thể chờ lock, khôi phục snapshot,<br/>hoặc từ chối theo repository policy
        Repo-->>B: Kết quả phụ thuộc trạng thái key
    end
~~~

Sơ đồ không khẳng định request B luôn đợi hoặc luôn lỗi. Cần kiểm thử repository thực tế. Điều cần đảm bảo là **dù B được xử lý lại, service không tạo booking thứ hai**.

### 10.2. Tránh action có side effect ở những bước người dùng có thể quay lại

Các state như `search`, `choose` và `review` nên chủ yếu đọc dữ liệu hoặc kiểm tra đầu vào. Không gửi thanh toán, tạo booking, trừ tồn kho hoặc gửi email trong một action có thể bị chạy lại do history/refresh mà không có bảo vệ idempotency.

Một thiết kế dễ kiểm soát:

~~~mermaid
stateDiagram-v2
    [*] --> search
    search --> choose: find
    choose --> review: next
    review --> confirmAction: confirm
    confirmAction --> completed: committed
    confirmAction --> review: rejected / needs consent
    completed --> [*]
~~~

`confirmAction` là nơi gọi service transaction. Dù action chỉ được đặt sau event confirm, service vẫn phải idempotent và kiểm tra trạng thái hiện tại trong database.

### 10.3. Optimistic locking cho dữ liệu được sửa

Nếu flow giữ một bản nháp dựa trên entity có thể bị người khác sửa, cân nhắc version field:

~~~java
@Entity
public class Booking {
    @Id
    private Long id;

    @Version
    private long version;
}
~~~

Đây là trích đoạn JPA; import phải phù hợp thế hệ Jakarta/Java EE của ứng dụng. Khi một tab submit bản cũ sau khi tab khác đã cập nhật, optimistic locking có thể phát hiện xung đột. Xử lý lỗi cần báo người dùng tải lại dữ liệu; không tự ghi đè thay đổi mới bằng snapshot cũ.

## 11. Session, đăng nhập và bảo mật khi nhiều tab cùng key

Các tab cùng origin thường gửi cùng session cookie. Vì vậy việc duplicate tab không tạo danh tính mới, cũng không tạo một phiên đăng nhập độc lập.

### 11.1. Execution key không phải thông tin xác thực

Không được xem `execution=...` là bằng chứng người dùng được quyền xem booking. Ở mỗi thao tác nhạy cảm:

- Lấy principal từ Spring Security context của request hiện tại.
- Kiểm tra quyền trên đúng booking/service/resource trong service.
- Kiểm tra trạng thái hiện tại và điều kiện nghiệp vụ trong transaction.
- Không tin `userId`, `ownerId`, giá hoặc role từ hidden field.
- Không lưu password, access token hoặc bí mật xác thực trong flowScope.

Một URL execution key cũ được gửi sau khi logout/login bằng tài khoản khác phải bị xử lý theo session/security policy hiện tại. Nếu repository tìm thấy execution, điều đó vẫn không cấp quyền trên dữ liệu của người dùng trước.

### 11.2. CSRF và POST event

Các event `next`, `back`, `confirm`, `cancel` thường được gửi bằng POST form. Nếu ứng dụng dùng session cookie, bật CSRF protection phù hợp của Spring Security và đảm bảo form gửi token. Duplicate tab có thể sao chép HTML chứa token cũ; token có thể còn hợp lệ hoặc hết hạn theo cơ chế CSRF/repository. Không bỏ qua CSRF vì request có execution key.

### 11.3. Không đặt dữ liệu nhạy cảm trong URL

Execution URL có thể xuất hiện trong:

- Browser history và bookmark.
- Access log, reverse proxy log, tracing.
- Header `Referer` khi điều hướng sang origin khác nếu policy cho phép.
- Ảnh chụp màn hình hoặc nội dung người dùng chia sẻ.

Không gắn email, số điện thoại, mã truy cập, giá trị bí mật hoặc dữ liệu cá nhân vào execution key/query string. Dùng HTTPS, cấu hình Referrer-Policy phù hợp và tránh log nguyên URL nếu query chứa dữ liệu không cần thiết.

## 12. Khi execution key cũ không còn hợp lệ

Một tab có thể để mở nhiều giờ rồi mới gửi event. Trong thời gian đó, session có thể hết hạn, execution kết thúc hoặc snapshot cũ bị dọn.

### 12.1. Các nguyên nhân phổ biến

| Nguyên nhân | Điều xảy ra |
| --- | --- |
| HTTP session timeout | Repository lưu trong session không còn execution |
| Flow đã kết thúc | Execution không còn nhận event tiếp theo |
| Snapshot limit bị vượt | Continuation cũ có thể bị loại bỏ |
| Application restart/deploy | Repository in-memory có thể mất dữ liệu |
| User logout hoặc đổi tài khoản | Session/security context thay đổi |
| Repository phân tán không nhất quán | Request tới node khác không tìm thấy snapshot |
| URL bị cắt hoặc sửa | Key không thể parse/lookup đúng |

Các lỗi có thể biểu hiện qua exception như `NoSuchFlowExecutionException` hoặc `FlowExecutionRestorationFailureException` tùy phiên bản và điểm lỗi. Hãy xử lý ở exception handler phù hợp thay vì phụ thuộc một tên exception cho mọi trường hợp.

### 12.2. UX khi tab cũ hết hạn

Thông báo nên nói rõ flow đã hết hạn và cho phép bắt đầu lại:

~~~text
Phiên thao tác này không còn khả dụng.
Nếu bạn đã xác nhận trước đó, hãy kiểm tra danh sách đặt chỗ.
Nếu chưa xác nhận, hãy bắt đầu một lượt mới.
~~~

Nếu thao tác confirm có thể đã commit nhưng response bị mất, **tra cứu theo idempotency key hoặc booking đã tạo trước khi yêu cầu người dùng gửi một yêu cầu mới**. Không tự động chuyển request POST cũ thành một flow mới rồi chạy lại action; làm vậy có thể tạo side effect lần nữa.

### 12.3. Khởi động lại mà không làm mất nghiệp vụ

Một flow execution hết hạn có thể được tạo lại từ đầu, nhưng dữ liệu nghiệp vụ đã commit phải còn trong database. Thiết kế:

1. Tách draft chưa xác nhận khỏi reservation đã lưu.
2. Có endpoint tra cứu trạng thái booking theo người dùng có quyền.
3. Dùng idempotency key để tìm kết quả commit không chắc chắn.
4. Khi cần tiếp tục draft sau timeout, lưu draft bền vững với owner, expiry và authorization; không phụ thuộc snapshot flow vô thời hạn.

## 13. Mẫu giao diện giúp người dùng tránh dùng nhầm execution

Một flow có thể cung cấp hai hành động rõ ràng:

~~~html
<!-- Tiếp tục đúng execution hiện tại -->
<form method="post" th:action="${flowExecutionUrl}">
    <button type="submit" name="_eventId_next">Tiếp tục</button>
</form>

<!-- Bắt đầu execution mới, có thể mở tab khác -->
<a th:href="@{/booking}" target="_blank" rel="noopener">
    Mở lượt đặt chỗ mới trong tab khác
</a>
~~~

Đây là snippet giao diện; endpoint `/booking` phải được `FlowHandlerMapping` ánh xạ tới flow ID tương ứng. Nếu flow được đặt dưới context path hoặc custom FlowUrlHandler, dùng URL thực tế do ứng dụng sinh.

### 13.1. Khi nào nên cho phép mở tab mới?

- Người dùng cần so sánh hai dịch vụ/đặt hai lịch riêng.
- Nhân viên xử lý nhiều khách hàng độc lập.
- Người dùng muốn giữ trang review hiện tại trong khi bắt đầu một booking khác.

Khi đó mỗi lần mở mới cần **một execution và draft mới**, có request ID riêng. Đừng copy URL hiện tại và kỳ vọng Web Flow tự tạo bản sao độc lập.

### 13.2. Khi nào nên khuyến khích dùng cùng tab?

- Quy trình đơn giản, không cần hai bản nháp đồng thời.
- Người dùng có thể dễ nhầm hai booking hoặc hai đối tượng.
- Hành trình có thao tác không thể đảo ngược, cần tập trung vào một giao dịch.

Có thể hiển thị cảnh báo trước khi rời trang nếu có dữ liệu chưa lưu. Nhưng cảnh báo UI chỉ cải thiện trải nghiệm; server vẫn phải xử lý key cũ và request lặp an toàn.

### 13.3. Không “khóa tab” bằng JavaScript như biện pháp bảo mật

Có thể dùng JavaScript để cảnh báo người dùng khi họ mở thêm tab hoặc rời trang, nhưng trình duyệt không cung cấp một định danh tab đáng tin cậy cho server. Người dùng có thể tắt script, gửi HTTP trực tiếp hoặc mở link ngoài. Không dùng `localStorage`, `sessionStorage` hay `window.name` làm bằng chứng quyền truy cập hoặc chống duplicate booking.

Nếu cần giới hạn số flow hoạt động, quản lý quy tắc ở server và thể hiện xung đột bằng message có thể hiểu; vẫn phải giữ transaction/idempotency cho request đồng thời.

## 14. Tổ chức flow để chịu được tab cũ

Một flow có thể giữ dữ liệu nhập trong `flowScope`, nhưng dữ liệu đó chỉ là **bản nháp của một execution**. Khi người dùng quay lại snapshot cũ hoặc một tab gửi event chậm, cần quyết định trường nào có thể dùng lại và trường nào phải đọc lại từ server.

| Loại dữ liệu | Nơi phù hợp | Khi xử lý request từ key cũ |
| --- | --- | --- |
| Từ khóa tìm kiếm | `flowScope` | Có thể dùng lại để tìm lại kết quả |
| Ngày người dùng chọn | `flowScope` | Validate lại nếu ngày có thể đã hết hạn |
| `serviceId` đã chọn | `flowScope` | Đọc lại dịch vụ, kiểm tra trạng thái/quyền |
| Giá hiển thị | Quote DTO trong flow | Đối chiếu giá hiện tại; không tin quote cũ mãi mãi |
| Owner/user identity | Spring Security context và service | Lấy principal của request hiện tại |
| Số chỗ còn lại | Database/catalog | Đọc lại khi commit |
| Booking đã xác nhận | Database | Kiểm tra trạng thái và idempotency |

Không dùng snapshot của flow như một bản sao đáng tin cậy của database. Snapshot phản ánh trạng thái flow tại một thời điểm; dữ liệu nghiệp vụ có thể đã đổi kể từ đó.

### 14.1. Đặt side effect sau bước xác nhận rõ ràng

Một flow dễ kiểm soát có thể tổ chức:

~~~xml
<view-state id="review" view="booking/review">
    <transition on="back" to="choose" bind="false"/>
    <transition on="confirm" to="commitBooking"/>
</view-state>

<action-state id="commitBooking">
    <evaluate expression="bookingActions.confirm(draft)"/>
    <transition on="success" to="completed"/>
    <transition on="unavailable" to="choose"/>
</action-state>
~~~

Đây là đoạn minh họa; cần action wrapper trả đúng outcome và service transaction. Đặt action sau event `confirm` giúp ranh giới dễ đọc, nhưng **không đảm bảo action chỉ chạy một lần** khi có duplicate tab, retry hoặc snapshot cũ. Idempotency vẫn là trách nhiệm của service/database.

### 14.2. Khi người dùng sửa lựa chọn ở tab khác

Nếu hai tab thực sự dùng cùng execution, một tab có thể gửi thay đổi draft và tab kia vẫn hiển thị dữ liệu client cũ. Khi tab thứ hai submit:

- Không giả định form body phản ánh bản draft mới nhất.
- Kiểm tra lại các field cần thiết và quy tắc state hiện tại.
- Nếu phát hiện dữ liệu cũ/xung đột, hiển thị thông báo và yêu cầu tải lại hoặc bắt đầu execution mới.
- Không âm thầm ghi đè thay đổi mới bằng giá trị từ form cũ.

Nếu nghiệp vụ cần chỉnh sửa đồng thời một bản ghi đã lưu, dùng version field/optimistic locking hoặc quy trình cập nhật có kiểm soát. Flow snapshot không phải cơ chế đồng bộ cộng tác thời gian thực.

## 15. Kiểm thử Duplicate tab và execution key

Để kiểm thử đúng, hãy dùng cùng session trình duyệt và thao tác thật trên hai tab. Test unit một service riêng lẻ không chứng minh hành vi browser history; test flow với repository giả cũng không chứng minh snapshot retention của production.

### 15.1. Quy trình tái hiện thủ công

1. Đăng nhập và mở flow bằng start URL, ví dụ `/booking`.
2. Đi qua một bước để trình duyệt hiển thị continuation URL có execution key.
3. Dùng lệnh Duplicate tab của trình duyệt.
4. Quan sát URL của hai tab; xác nhận chúng có cùng continuation key tại thời điểm nhân bản.
5. Ở tab A, chọn một dịch vụ hoặc gửi event `next`; ghi lại URL/key mới sau response.
6. Không reload tab B; gửi một event từ tab B với URL/key cũ.
7. Ghi nhận kết quả: snapshot được khôi phục, request bị từ chối, hay execution không còn.
8. Lặp lại với hai request gần như đồng thời (ví dụ double-click hoặc công cụ kiểm thử HTTP).
9. Kiểm tra database: không có booking trùng, không vượt số chỗ, trạng thái cuối nhất quán.
10. Mở start URL `/booking` trong tab thứ ba; xác nhận nó tạo execution mới và draft riêng.

Không dùng dữ liệu khách hàng thật để thử request replay hoặc cạnh tranh. Dùng database/test account riêng.

### 15.2. Ma trận test tối thiểu

| ID | Kịch bản | Kết quả cần xác minh |
| --- | --- | --- |
| B01 | GET start URL lần đầu | Flow execution mới bắt đầu ở state đầu |
| B02 | Duplicate tab khi đang ở view-state | Tab mới có cùng continuation URL/key ban đầu |
| B03 | Tab A submit và nhận key mới | Tab B không tự đổi URL theo A |
| B04 | Tab B gửi event từ key cũ khi snapshot còn | Hành vi khôi phục/nhánh được xác định theo repository |
| B05 | Tab B gửi key cũ sau khi snapshot bị dọn | Lỗi expired execution được xử lý thân thiện |
| B06 | Hai request cùng key chạy gần đồng thời | Lock/repository policy hoạt động, không gây state corruption |
| B07 | Hai tab cùng gửi confirm với cùng request ID | Chỉ một booking, retry nhận cùng receipt |
| B08 | Hai execution mới có request ID khác nhau | Có thể tạo hai booking độc lập nếu nghiệp vụ cho phép |
| B09 | Browser Back sau transition | Kết quả đúng theo snapshot/history policy |
| B10 | Refresh sau POST đã redirect | Không tạo side effect thứ hai |
| B11 | Double-click nút confirm | Idempotency bảo vệ giao dịch |
| B12 | Logout ở tab A, gửi key cũ ở tab B | Quyền được đánh giá theo session/principal hiện tại |
| B13 | Cùng key nhưng session cookie khác | Không truy cập execution của session khác nếu repository ràng buộc theo session |
| B14 | Session timeout trong tab B | Hiển thị hướng bắt đầu lại/tra cứu kết quả |
| B15 | Vượt snapshot retention limit | Key cũ có hành vi dự kiến và được xử lý |
| B16 | Mở start URL trong tab mới | Tạo execution mới, draft độc lập |
| B17 | Client sửa `serviceId`/`ownerId` | Service authorization và validation từ chối dữ liệu không hợp lệ |
| B18 | POST thiếu CSRF token | Spring Security chặn theo policy |
| B19 | Commit xong nhưng response bị mất | Retry tra booking cũ bằng idempotency key |
| B20 | Nhiều node xử lý cùng session/execution | Repository/session store nhất quán hoặc lỗi được xử lý rõ |

### 15.3. Quan sát log

Để phân tích hai tab, nên có correlation ID cho request và log có cấu trúc gồm:

- Flow ID và state ID (nếu có thể lấy an toàn).
- Kết quả event/action: success, stale, unavailable, expired.
- Business request ID ở dạng đã che/mã hóa phù hợp.
- Thời gian xử lý và node instance.
- Kết quả transaction: committed, rejected, conflict.

Không log nguyên session ID, CSRF token, access token hoặc toàn bộ URL nếu query có thể chứa thông tin nhạy cảm. Execution key cũng nên được xử lý theo chính sách log của hệ thống; chỉ ghi khi thực sự cần và cân nhắc mask.

## 16. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Duplicate tab thấy cùng dữ liệu | URL trỏ cùng execution key | Dùng start URL nếu cần hành trình độc lập |
| Tab A chuyển bước, tab B vẫn ở URL cũ | URL mỗi tab có history riêng | Không kỳ vọng URL tự đồng bộ; xử lý stale key |
| Tab B báo flow execution không tồn tại | Snapshot/session đã hết hạn hoặc bị dọn | Hiển thị thông báo, cho bắt đầu lại/tra cứu booking |
| Tab B quay về dữ liệu cũ | Snapshot cũ còn được repository giữ | Service đọc lại dữ liệu nghiệp vụ và kiểm tra version |
| Hai lần confirm tạo hai booking | Thiếu idempotency/unique constraint | Tạo request ID server-side, unique key và transaction |
| Booking bị tạo dù người dùng thấy lỗi | Commit đã xảy ra nhưng response/flow lỗi | Tra cứu theo idempotency key; không retry với key mới |
| Hai tab cập nhật đè nhau | Dùng chung execution hoặc entity cũ | Tách execution, dùng optimistic locking/version |
| Start link tiếp tục flow cũ | Link đang trỏ flowExecutionUrl | Dùng flow start URL không có execution key |
| Start link mở flow nhưng mất draft cũ | Người dùng điều hướng khỏi execution cũ | Mở start URL trong tab mới hoặc cảnh báo trước khi rời |
| Logout nhưng key cũ vẫn tìm được snapshot | Repository và session policy chưa đồng bộ | Kiểm tra session invalidation và authorization ở service |
| Chỉ node A tìm được execution | Repository/session không chia sẻ đúng trong cluster | Cấu hình sticky session hoặc repository phân tán phù hợp |
| Browser Back gọi lại thao tác ghi | Action có side effect không idempotent | Tách commit và bảo vệ bằng idempotency/database |

### 16.1. Phân biệt lỗi execution với lỗi nghiệp vụ

- **Execution lỗi:** không tìm được flow/snapshot, key sai, session hết hạn. Người dùng cần bắt đầu lại hoặc phục hồi execution nếu hệ thống hỗ trợ.
- **Lỗi nghiệp vụ:** dịch vụ hết chỗ, booking đã xác nhận, người dùng không có quyền. Execution có thể vẫn hợp lệ; flow nên hiển thị thông báo và hướng đi phù hợp.
- **Kết quả không chắc chắn:** database có thể đã commit nhưng response bị mất. Trước khi tạo lệnh mới, tra cứu theo idempotency key.

Không ánh xạ tất cả các lỗi thành “flow hết hạn”. Cần phân biệt để không yêu cầu người dùng đặt lại một booking đã thành công.

## 17. Bài tập thực hành

### Bài A — chứng minh hai tab dùng chung execution key

Tạo flow `booking` có hai view-state `details` và `review`. Mở `review`, duplicate tab, so sánh URL hai tab. Gửi event `back` từ tab A rồi thử tiếp tục tab B. Ghi lại trạng thái và exception theo repository đang dùng.

**Đạt khi:** giải thích được URL/key nào được gửi, tab nào nhận response mới và tại sao tab kia không tự cập nhật.

### Bài B — thêm nút tạo execution mới

Thêm link `/booking` với `target="_blank"` trên trang review. Mở tab mới và xác minh flow registry tạo execution mới, draft trống và request ID mới. Đóng tab mới rồi tiếp tục tab cũ; xác minh hai execution không làm mất dữ liệu của nhau.

**Đạt khi:** phân biệt được cùng HTTP session với execution độc lập.

### Bài C — chống double confirm

Thêm request ID được server sinh vào draft. Tạo unique constraint `(user_id, request_id)`. Gửi hai request confirm gần đồng thời với cùng key, kiểm tra chỉ có một reservation. Gửi lại sau khi response đầu bị mô phỏng mất; service trả receipt cũ.

**Đạt khi:** test race chạy với database thực hoặc database integration tương đương production, không chỉ mock repository.

### Bài D — stale key và snapshot retention

Điều chỉnh giới hạn snapshot trong môi trường test, tạo nhiều transition, giữ một tab cũ và gửi request từ key đã cũ. Quan sát exception/response, sau đó tạo đường phục hồi cho người dùng.

**Đạt khi:** không làm rò dữ liệu, không tạo booking mới ngoài ý muốn và có link bắt đầu flow mới.

### Bài E — bảo mật khi đổi tài khoản

Mở flow với User A, duplicate tab, logout ở một tab rồi login User B. Gửi request từ tab còn lại. Xác minh principal hiện tại, session lifecycle và quyền trên bản ghi; không dựa vào execution key để cấp quyền.

## 18. Checklist triển khai

- [ ] Phân biệt flow start URL và continuation URL.
- [ ] Form trong view-state dùng URL execution do Web Flow cung cấp.
- [ ] Link tạo hành trình mới đi tới start URL, không mang execution key cũ.
- [ ] Không giả định Duplicate tab tạo execution độc lập.
- [ ] Đã kiểm thử snapshot restore và stale key với repository thực tế.
- [ ] Đã xác minh giới hạn execution/snapshot và tác động tới session/bộ nhớ.
- [ ] Dữ liệu nghiệp vụ quan trọng được đọc lại từ service/database ở thời điểm commit.
- [ ] Action có side effect nằm sau event xác nhận rõ ràng.
- [ ] Execution key không được dùng làm authentication/authorization.
- [ ] CSRF được bảo vệ trên các POST event.
- [ ] Service kiểm tra principal, quyền, trạng thái và version.
- [ ] Idempotency key được sinh phía server và không bind từ client.
- [ ] Database có unique constraint phù hợp và transaction xử lý cạnh tranh.
- [ ] Side effect bên ngoài có idempotency/outbox hoặc cơ chế bù trừ.
- [ ] Flow hết hạn có thông báo và đường bắt đầu lại.
- [ ] Booking đã commit có thể tra cứu độc lập với flow execution.
- [ ] Có test hai tab, request đồng thời, browser Back, refresh và session timeout.
- [ ] Log không chứa token, session ID hoặc dữ liệu cá nhân không cần thiết.

## 19. Câu hỏi tự kiểm tra

**1. Duplicate tab có tự tạo flow execution mới không?** Không. Nếu URL được sao chép chứa continuation key, tab mới có thể tiếp tục cùng execution/snapshot.

**2. Hai tab có cùng session nghĩa là cùng flow execution không?** Không. Một session có thể chứa nhiều execution; cần xem execution key/URL.

**3. Muốn mở một flow mới phải dùng URL nào?** Dùng start URL được FlowHandlerMapping ánh xạ tới flow ID, không dùng continuation URL có execution key.

**4. Vì sao tab B vẫn gửi key cũ sau khi tab A chuyển bước?** Mỗi tab có lịch sử URL riêng; server không tự cập nhật URL trong tab khác.

**5. Request từ key cũ luôn bị từ chối phải không?** Không. Snapshot có thể còn và được khôi phục, hoặc đã bị dọn; hành vi phụ thuộc repository/history policy và phiên bản.

**6. Execution key có thay thế idempotency key không?** Không. Execution key điều hướng flow; idempotency key nhận diện một lệnh nghiệp vụ có thể gửi lại.

**7. PRG có ngăn double-click hoặc hai tab cùng confirm không?** Không đủ. Cần service idempotent, transaction và ràng buộc database.

**8. Có thể dựa vào JavaScript để biết tab nào là bản sao không?** Không nên. Server không nhận một tab identity chuẩn hóa, đáng tin cậy từ trình duyệt.

**9. Nếu flow hết hạn nhưng booking có thể đã commit thì sao?** Tra cứu theo business ID/idempotency key trước khi yêu cầu tạo lệnh mới.

**10. Vì sao phải test trên repository production tương tự?** Snapshot retention, lock, session storage và phân tán có thể làm hành vi của key cũ khác nhau giữa test đơn giản và production.

## 20. Tài liệu tham khảo

1. [Spring Web Flow Reference Guide 3.0.2](https://docs.spring.io/spring-webflow/docs/3.0.2/reference/) — Flow execution, continuation, flow execution repository, snapshot/history, executor và cấu hình repository.
2. [Spring Web Flow API 3.0.2](https://docs.spring.io/spring-webflow/docs/3.0.2/api/) — `FlowExecutionKey`, `FlowExecutionRepository`, `FlowExecutionLock` và các API liên quan.
3. [Spring Web Flow 2.5.1 Reference Guide](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/htmlsingle/) — đối chiếu hành vi ở dòng Spring 5/Web Flow 2.5.
4. [Spring Web Flow 4.0.2 Reference Guide](https://docs.spring.io/spring-webflow/docs/4.0.2/reference/) — đối chiếu dòng Spring 7/Web Flow 4.
5. [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — bảo vệ POST form sử dụng session cookie.
6. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — phân quyền theo đối tượng; kết hợp unique constraint và transaction ở tầng dữ liệu.

**Điểm cần nhớ:** Duplicate tab thường sao chép URL continuation và cookie, nên có thể dùng lại **cùng flow execution key**. Muốn có hành trình độc lập, mở flow bằng **start URL** để tạo execution mới. Nhưng dù hai tab dùng cùng hay khác execution, trạng thái booking vẫn phải được bảo vệ ở service/database bằng kiểm tra quyền, transaction, version và idempotency; snapshot/history chỉ hỗ trợ điều hướng và phục hồi flow.
