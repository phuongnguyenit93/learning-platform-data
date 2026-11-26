# Luồng tương tác có trạng thái qua nhiều yêu cầu HTTP

> **Chương:** Bản đồ Web Flow  
> **Chủ đề:** Cách Spring Web Flow duy trì một hành trình người dùng xuyên qua nhiều HTTP request, từ khởi tạo flow execution, xử lý event và transition đến lưu, khôi phục và kết thúc trạng thái.

## 1. Vấn đề: HTTP độc lập, hành trình người dùng thì liên tục

HTTP hoạt động theo mô hình yêu cầu và phản hồi: trình duyệt gửi một request, máy chủ xử lý rồi trả response. Request tiếp theo là một lần trao đổi mới; bản thân giao thức không mang theo đối tượng Java, biến cục bộ hay trạng thái chương trình của request trước.

Tuy nhiên, trải nghiệm thực tế thường kéo dài qua nhiều request. Xét chức năng **đặt dịch vụ**:

1. Người dùng nhập thông tin liên hệ.
2. Người dùng chọn gói dịch vụ.
3. Người dùng xem lại thông tin.
4. Người dùng xác nhận và nhận mã đơn.

Từ góc nhìn trình duyệt, đây có thể là bốn hoặc nhiều request HTTP. Từ góc nhìn nghiệp vụ, đây là **một hành trình có trạng thái**: hệ thống phải biết bước hiện tại, dữ liệu đã nhập, các bước được phép quay lại và điều kiện để xác nhận.

Nếu chỉ dùng các controller độc lập, nhóm phát triển phải tự trả lời hàng loạt câu hỏi: dữ liệu của bước trước lưu ở đâu; truy cập trực tiếp URL của bước cuối có hợp lệ không; submit bị lặp xử lý ra sao; cần làm gì khi session hết hạn; hai tab có ghi đè bản nháp của nhau không?

**Spring Web Flow (SWF)** cung cấp mô hình để nối các request HTTP thành một **flow execution** nhất quán, quản lý trạng thái và điều hướng bằng **state**, **event** và **transition**.

## 2. Phân biệt ba lớp: HTTP request, session và flow execution

Ba khái niệm này liên quan với nhau nhưng không phải là một.

| Lớp | Có ý nghĩa gì? | Vòng đời điển hình |
| --- | --- | --- |
| **HTTP request** | Một lần trình duyệt giao tiếp với máy chủ | Chỉ trong một lần request/response |
| **HTTP session** | Ngữ cảnh phiên mà máy chủ liên kết với một trình duyệt/khách hàng theo cấu hình | Qua nhiều request, cho đến khi hết hạn hoặc bị hủy |
| **Flow execution** | Một lần chạy cụ thể của một flow, có state hiện tại và dữ liệu riêng | Từ lúc bắt đầu flow đến khi kết thúc hoặc không còn khôi phục được |

Một HTTP session **có thể chứa nhiều flow execution**. Ví dụ, người dùng mở hai tab: tab A đang đặt lịch khám, tab B đang đổi thông tin tài khoản. Mỗi tab có thể tiếp tục một flow khác mà không dùng chung bản nháp.

Ngược lại, **flow execution không đồng nghĩa với HTTP session**. Session thường chỉ là một phần của cơ chế lưu hoặc tra cứu trạng thái của Web Flow; cách lưu có thể được cấu hình. Khi session hết hạn, không thể mặc nhiên khôi phục một flow chỉ nhờ còn URL cũ.

### 2.1. Có trạng thái ở ứng dụng không làm HTTP trở thành giao thức có trạng thái

HTTP vẫn xử lý từng request riêng. Cái được duy trì là **ngữ cảnh ứng dụng**: server khôi phục đối tượng mô tả hành trình trước khi quyết định phản hồi. Các ứng dụng web khác cũng làm tương tự bằng session, cơ sở dữ liệu hoặc token; Web Flow cung cấp một **mô hình điều phối có cấu trúc** cho nhiệm vụ đó.

Điều cần nhớ: không có servlet request, Java thread hay database transaction nào phải mở liên tục trong lúc người dùng ngồi đọc một form.

## 3. Flow definition và flow execution

**Flow definition** là bản mô tả quy trình: những state nào tồn tại và event nào chuyển từ state này sang state khác. Nó thường được khai báo bằng XML và được đăng ký trong **FlowDefinitionRegistry**.

**Flow execution** là một lần chạy của bản mô tả ấy, gồm ít nhất:

- Flow hiện hành và state đang hoạt động.
- Dữ liệu theo scope, chẳng hạn bản nháp đơn đặt dịch vụ.
- Ngữ cảnh execution cần thiết để xử lý event và transition tiếp theo.
- Thông tin về subflow hoặc các snapshot/continuation nếu cấu hình hỗ trợ.

Hai người dùng có thể thực hiện cùng định nghĩa flow checkout, nhưng mỗi người có execution riêng với dữ liệu khác nhau. Một người cũng có thể mở hai execution của cùng một flow.

~~~mermaid
flowchart TD
    D["Định nghĩa checkout flow"] --> A["Execution A: contact, email A"]
    D --> B["Execution B: review, email B"]
    A --> SA["Các request của tab A"]
    B --> SB["Các request của tab B"]
~~~

Mô hình này giúp tách **cấu trúc điều hướng** dùng chung khỏi **dữ liệu phiên chạy** của từng người.

## 4. Một flow đi qua các HTTP request như thế nào?

Xét hành trình gồm ba view-state **contact → package → review**, tiếp theo là action-state **submit** và end-state **completed**.

~~~mermaid
flowchart LR
    S((Start)) --> C["contact"]
    C -->|next| P["package"]
    P -->|back| C
    P -->|next| R["review"]
    R -->|edit| C
    R -->|confirm| A["submit"]
    A -->|success| E((completed))
    C -->|cancel| X((cancelled))
    P -->|cancel| X
    R -->|cancel| X
~~~

Giả sử ứng dụng ánh xạ flow này đến đường dẫn **/checkout**. Các khóa execution sau đây chỉ để minh họa, không phải giá trị cố định.

| Mốc | Request từ trình duyệt | Công việc trong Web Flow | Kết quả |
| --- | --- | --- | --- |
| T0 | GET /checkout | Tìm flow definition, tạo flow execution, vào state contact | Render trang nhập liên hệ, cấp khóa execution |
| T1 | POST /checkout với event next và dữ liệu liên hệ | Khôi phục execution, bind form, validate, chuyển contact → package | Trả trang chọn gói, lưu trạng thái mới |
| T2 | POST /checkout với event next và gói đã chọn | Khôi phục execution, cập nhật bản nháp, chuyển package → review | Render trang xem lại |
| T3 | POST /checkout với event edit | Khôi phục execution, chuyển review → contact | Render form để chỉnh sửa |
| T4 | POST /checkout với event next, rồi đi lại đến review | Cập nhật bản nháp và điều hướng theo transition hợp lệ | Render review với dữ liệu đã sửa |
| T5 | POST /checkout với event confirm | Khôi phục execution, qua action submit, gọi service | Đến completed nếu lưu thành công |

Không phải request nào cũng tạo một flow execution mới. **T0** thường bắt đầu một execution, còn **T1–T5** tiếp tục execution đó bằng khóa/ngữ cảnh do Web Flow cấp.

### 4.1. Một request tiếp tục flow trông ra sao?

Request gửi từ một form có thể tương tự:

~~~http
POST /checkout?execution=e1s1 HTTP/1.1
Content-Type: application/x-www-form-urlencoded

_eventId=next&email=an%40example.com
~~~

Trong ví dụ:

- **execution=e1s1** là mã minh họa giúp framework xác định lần chạy/snapshot cần tiếp tục. Khóa do Web Flow tạo, có thể thay đổi sau từng bước và không nên tự sinh.
- **_eventId=next** biểu diễn ý định của người dùng, được dùng để tìm transition hợp lệ tại state hiện hành.
- **email=...** là dữ liệu cần binding vào model nếu field được cho phép và form đang ở state phù hợp.

Form còn có thể gửi sự kiện qua tên nút, chẳng hạn **_eventId_next**. Cách gắn execution key vào URL và các field form phụ thuộc view renderer và cấu hình thực tế. Ứng dụng thật cần dùng **URL và khóa hiện thời do Web Flow cung cấp**, không chép mã e1s1 vào template.

### 4.2. Luồng xử lý bên trong máy chủ

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant M as Spring MVC
    participant E as FlowExecutor
    participant R as Execution Repository
    participant S as Service

    U->>B: Nhấn Next ở contact
    B->>M: POST + execution key + event + form
    M->>E: Chuyển request đến flow
    E->>R: Tra cứu/khôi phục execution
    R-->>E: State contact + flow data
    E->>E: Binding, validation, chọn transition
    E->>E: Chuyển đến state package
    E->>R: Lưu execution/snapshot theo cấu hình
    E-->>M: View package và ngữ cảnh tiếp tục
    M-->>B: HTTP response
    B-->>U: Hiển thị trang chọn gói

    U->>B: Xác nhận ở bước review
    B->>M: POST confirm với execution key mới
    M->>E: Tiếp tục flow
    E->>R: Khôi phục execution
    E->>S: Gọi submit(draft)
    S-->>E: Kết quả nghiệp vụ
    E-->>M: Chuyển đến completed
    M-->>B: HTTP response kết quả
~~~

Sơ đồ diễn tả **thứ tự logic**, không khóa chặt framework vào một cơ chế lưu trạng thái hay kiểu response cụ thể. Web Flow có thể redirect trước khi render view tùy cấu hình, vì vậy trình duyệt có thể phát sinh thêm GET sau POST.

## 5. Flow execution được tạo, tạm dừng và kết thúc

Một lần chạy flow có ba giai đoạn chính.

**Khởi tạo (start).** Khi người dùng truy cập một URL khởi động flow, FlowExecutor tìm định nghĩa tương ứng, tạo ngữ cảnh execution, thiết lập dữ liệu ban đầu, thực hiện các hành động khởi tạo và đi đến state đầu tiên. Nếu state đầu tiên là view-state, ứng dụng render giao diện cho người dùng.

**Tạm dừng/chờ (pause).** Ở view-state, framework cần chờ người dùng tương tác. Ngữ cảnh execution được lưu qua cơ chế repository phù hợp để request sau có thể tiếp tục. Trong thời gian chờ, máy chủ không chiếm giữ một thread để ngồi đợi người dùng.

**Tiếp tục (resume).** Request tiếp theo cung cấp ngữ cảnh định vị flow và event. Framework khôi phục trạng thái, cập nhật model theo rules, chọn transition và có thể chạy liên tiếp action-state/decision-state cho đến view-state kế tiếp hoặc end-state.

**Kết thúc (end).** Khi gặp end-state, flow hoàn thành. Dữ liệu có vòng đời thuộc execution không còn được dùng như một bản nháp đang hoạt động. Nghiệp vụ đã commit vào database vẫn tồn tại độc lập.

Một flow có thể kết thúc bằng event **completed**, **cancelled** hoặc các kết thúc nghiệp vụ khác. Hủy flow không mặc nhiên rollback các giao dịch database đã commit trước đó.

## 6. Ví dụ khai báo flow cho một form nhiều bước

Ví dụ sau minh họa cấu trúc điều hướng, chưa bao gồm toàn bộ cấu hình Spring MVC, bean/service, bảo mật, view và validation cần thiết để thành ứng dụng chạy hoàn chỉnh:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <!-- Mỗi execution có bản nháp riêng. -->
    <var name="draft" class="com.example.checkout.CheckoutDraft"/>

    <view-state id="contact" view="checkout/contact" model="draft">
        <binder>
            <binding property="email" required="true"/>
            <binding property="phone"/>
        </binder>
        <transition on="next" to="package"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="package" view="checkout/package" model="draft">
        <binder>
            <binding property="packageCode" required="true"/>
        </binder>
        <transition on="back" to="contact" bind="false"/>
        <transition on="next" to="review"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="edit" to="contact" bind="false"/>
        <transition on="confirm" to="submit" bind="false"/>
        <transition on="cancel" to="cancelled" bind="false"/>
    </view-state>

    <action-state id="submit">
        <evaluate expression="checkoutService.submit(draft)"/>
        <transition on="success" to="completed"/>
    </action-state>

    <end-state id="completed" view="checkout/completed"/>
    <end-state id="cancelled" view="checkout/cancelled"/>
</flow>
~~~

Các điểm cần đọc kỹ:

1. **var draft** tạo một model làm việc của flow, không phải thuộc tính Java static dùng chung.
2. **view-state** tạo điểm chờ giữa các request: khi ở contact, người dùng cần nhập liệu và gửi event mới có thể chuyển sang package.
3. **binder** giới hạn thuộc tính được phép bind ở state tương ứng. Đây là lớp bảo vệ cần thiết khi dữ liệu request không đáng tin.
4. **transition on="next"** chỉ có ý nghĩa trong state đã khai báo nó. Người dùng không được quyền nhảy đến bất cứ state nào chỉ bằng cách gửi event tên next.
5. **bind="false"** phù hợp với event chỉ để điều hướng như back/cancel, tránh ràng buộc phải binding và validation form trước khi quay lại/hủy.
6. **action-state submit** chịu trách nhiệm gọi service. Ví dụ giả định evaluate hoàn thành bình thường và phát sinh outcome success phù hợp; lỗi nghiệp vụ và exception cần được thiết kế xử lý riêng.
7. **end-state** phân biệt hoàn thành và hủy. Khi đã kết thúc, không nên tiếp tục dùng khóa của execution như thể đang ở một view-state.

Trong ứng dụng thật, service submit phải kiểm tra lại tính hợp lệ của toàn bộ bản nháp, quyền thực hiện, khả năng tiếp nhận đơn và tính idempotent. Cấu trúc flow giúp diễn đạt hành trình nhưng không thay thế các kiểm tra nghiệp vụ.

## 7. State trong flow khác dữ liệu của form như thế nào?

Khi người dùng đang ở **package**, state hiện hành là một phần của máy trạng thái; còn **email** đã nhập ở contact là dữ liệu. Hai loại thông tin phải được quản lý đồng thời:

- **Control state:** bước nào đang hoạt động, event nào được cho phép, transition nào sẽ được chọn.
- **Data state:** draft, lựa chọn, thông báo, dữ liệu phục vụ các bước tiếp theo.

Ví dụ, người dùng nhấn **back** từ package về contact. Control state thay đổi, nhưng draft.email thường vẫn cần được giữ lại để form hiển thị giá trị cũ. Nếu người dùng đổi email và nhấn next, hệ thống cập nhật draft rồi chuyển sang package lần nữa.

### 7.1. Vì sao phải có binding và validation ở từng request?

Trình duyệt gửi **chuỗi ký tự và các tham số không đáng tin**. Web Flow cần chuyển dữ liệu thành giá trị có kiểu, kiểm tra field được phép và validate trước khi đi tiếp.

Một quy trình nên phân biệt:

| Giai đoạn | Ví dụ kiểm tra | Mục đích |
| --- | --- | --- |
| Binding | Chỉ nhận email và phone tại contact | Tránh cập nhật field ngoài phạm vi state |
| Validation của bước | Email bắt buộc, đúng định dạng | Không chuyển đến package với dữ liệu contact sai |
| Validation trước commit | Gói dịch vụ còn hiệu lực, email có quyền dùng, giá mới nhất | Ngăn ghi dữ liệu không hợp lệ hoặc đã lỗi thời |

Khi validation thất bại, hành vi thường mong muốn là giữ ở view-state đang nhập, hiển thị lỗi và cho sửa dữ liệu. Validation trước commit luôn thuộc về tầng nghiệp vụ, bởi dữ liệu và điều kiện bên ngoài có thể thay đổi giữa các request.

## 8. Phân bổ dữ liệu vào scope phù hợp

Web Flow cung cấp nhiều scope để quản lý dữ liệu theo vòng đời thay vì tùy tiện nhét tất cả vào HTTP session.

| Scope | Vòng đời khái quát | Ví dụ |
| --- | --- | --- |
| **requestScope** | Trong một lần xử lý yêu cầu flow | Kết quả truy vấn tạm |
| **flashScope** | Dữ liệu tạm phục vụ phản hồi/chuyển view kế tiếp theo cơ chế flash của Web Flow | Thông báo thao tác thành công |
| **viewScope** | Trong lúc một view-state còn đang hoạt động | Các lựa chọn hiển thị riêng trên trang package |
| **flowScope** | Trong một flow execution | CheckoutDraft chứa thông tin nhiều bước |
| **conversationScope** | Qua các flow/subflow thuộc cùng conversation | Ngữ cảnh chung cần trao đổi giữa flow cha và con |

**Flow scope** là lựa chọn tự nhiên cho bản nháp dùng qua nhiều view-state. Nếu chỉ một trang cần danh sách gợi ý ngắn hạn, **view scope** có thể hợp lý hơn. Nếu tác vụ con cần kết quả từ tác vụ cha, thiết kế **input/output** rõ ràng giữa flow và subflow sẽ dễ kiểm soát hơn việc để cả hai tự ý sửa nhiều biến chia sẻ.

### 8.1. Những thứ không nên cất lâu trong flowScope

Không nên lưu vào flowScope một kết nối database, stream đang mở, session ORM đang hoạt động, object cực lớn hoặc dữ liệu nhạy cảm không cần thiết. Những đối tượng như vậy khó quản lý vòng đời, có thể gây lỗi khi snapshot/serialize và tốn tài nguyên trên máy chủ.

Nên lưu **dữ liệu làm việc nhỏ gọn**, thường là ID, lựa chọn và DTO cần cho các bước còn lại. Nếu người dùng cần quay lại sau nhiều ngày, hãy lưu **bản nháp bền vững** vào database theo nghiệp vụ, thay vì kỳ vọng flow execution còn tồn tại mãi.

## 9. Khôi phục flow execution: repository và khóa tiếp tục

Khi một view-state cần chờ người dùng, Web Flow phải có cách nhận diện lại lần chạy ở request sau. **FlowExecutionRepository** là cơ chế quản lý việc lưu, lấy lại và tiếp tục flow execution; chi tiết phụ thuộc cấu hình repository và phiên bản Web Flow.

Một chu trình đơn giản là:

~~~text
GET /checkout
  -> start flow
  -> render contact + execution key K1

POST /checkout (execution=K1, event=next)
  -> restore execution
  -> bind/validate email
  -> transition contact -> package
  -> save execution
  -> render/redirect với key K2

POST /checkout (execution=K2, event=next)
  -> restore execution
  -> bind/validate packageCode
  -> transition package -> review
  -> save execution
  -> render/redirect với key K3
~~~

K1, K2 và K3 tượng trưng cho các ngữ cảnh tiếp tục ở các thời điểm khác nhau. Không nên dựa vào hình dạng, thứ tự hay việc khóa có luôn thay đổi hay không; đó là chi tiết triển khai của framework/repository.

### 9.1. Snapshot và continuation

Một số cấu hình repository có thể lưu các **snapshot** của flow execution, cho phép khôi phục một trạng thái trước đó khi người dùng gửi khóa cũ hợp lệ. Số lượng snapshot, khả năng quay lại, cách dọn dẹp và xử lý lỗi là các lựa chọn cấu hình.

Điểm phân biệt quan trọng:

- **Event back** là transition được khai báo và kiểm soát ở state hiện tại.
- **Nút Back của trình duyệt** yêu cầu trang trước từ lịch sử; có thể dẫn đến submit với một khóa cũ.
- **Khôi phục snapshot cũ** là hành vi của repository, không bảo đảm một thao tác nghiệp vụ đã commit được đảo ngược.

Vì vậy, khi thiết kế hành trình cần kiểm thử cả **nút Back do ứng dụng cung cấp** lẫn **Back/Refresh của trình duyệt**.

### 9.2. Nếu flow execution không còn tồn tại

Trường hợp thường gặp: người dùng mở trang review, rời máy trong thời gian dài rồi nhấn confirm sau khi HTTP session hết hạn. Máy chủ có thể không còn tìm thấy execution tương ứng. Hành vi đúng phải được thiết kế cụ thể: thông báo phiên đã hết, cho bắt đầu lại, hoặc phục hồi từ bản nháp đã lưu nếu sản phẩm có chức năng đó.

**Không nên tự khởi tạo một flow mới rồi âm thầm coi request confirm cũ là hợp lệ.** Request có thể mang dữ liệu lỗi thời, thiếu ngữ cảnh hoặc không còn được phép thực hiện.

## 10. Refresh, redirect và gửi lại form

Khi người dùng submit form, trình duyệt có thể tải lại response, hoặc người dùng bấm nút gửi nhiều lần. Đây là hai vấn đề khác nhau:

1. **Refresh sau POST** có thể khiến trình duyệt hỏi gửi lại dữ liệu; cấu hình redirect sau một số thao tác giúp cải thiện trải nghiệm.
2. **Submit trùng ở tầng nghiệp vụ** vẫn có thể xảy ra do double-click, retry mạng hoặc hai request đồng thời. Redirect không đủ để bảo đảm tạo đúng một đơn.

Web Flow có cơ chế quản lý việc render/redirect khi tạm dừng ở view-state và tiếp tục execution. Cách hoạt động cụ thể phụ thuộc cấu hình. Nếu ứng dụng dùng mẫu **Post/Redirect/Get**, trình duyệt được hướng đến một GET để lấy view sau POST, giảm rủi ro refresh gửi lại form.

Tuy nhiên, mọi action có tác dụng ghi dữ liệu quan trọng vẫn cần **idempotency ở service hoặc database**.

### 10.1. Ví dụ tránh tạo đơn trùng

Giả sử draft có **requestId** ổn định được cấp khi bắt đầu flow. Service có thể tạo đơn theo logic:

~~~text
submit(draft):
  kiểm tra xác thực, quyền và dữ liệu hiện hành
  bắt đầu transaction
  tra cứu đơn có requestId của draft
  nếu đã tồn tại: trả về đơn cũ
  nếu chưa tồn tại:
      tạo đơn mới với unique(requestId)
      commit transaction
      trả về đơn mới
~~~

Đây là pseudocode về nguyên tắc. Trong hệ thống thực, cần dùng unique constraint và xử lý cạnh tranh giữa các transaction; thao tác tra cứu trước rồi insert đơn thuần chưa đủ để tránh race condition.

Flow điều hướng có thể nhận kết quả đã tạo đơn và đi đến completed, trong khi service vẫn an toàn nếu HTTP request bị gửi lại.

## 11. Cùng một session có nhiều tab thì sao?

Hai tab có thể cùng mở **checkout**, nhưng nếu mỗi tab khởi tạo một flow execution mới thì hai bản nháp được tách biệt theo khóa/ngữ cảnh execution tương ứng.

~~~mermaid
flowchart TD
    H["HTTP Session của trình duyệt"] --> A["Tab A: flow execution X"]
    H --> B["Tab B: flow execution Y"]
    A --> DA["flowScope.draft: email A, package A"]
    B --> DB["flowScope.draft: email B, package B"]
~~~

Tình huống phức tạp hơn xảy ra khi hai tab cùng sử dụng **một execution key** vì trang đã được nhân bản, bookmark hoặc restore. Khi đó, hai request có thể cạnh tranh trên một execution và gửi event dựa trên hai state khác nhau.

Web Flow/repository có cơ chế điều phối và các giới hạn khôi phục theo cấu hình, nhưng thiết kế ứng dụng vẫn phải xác định rõ: hiển thị thông báo state cũ, yêu cầu tải lại, tạo flow riêng, hay phục hồi một snapshot hợp lệ.

Nếu cần ngăn hai tác vụ cùng sửa một **bản ghi database**, phải dùng cơ chế versioning/optimistic locking hoặc kiểm soát đồng thời ở tầng dữ liệu. Hai flowScope tách nhau không giải quyết xung đột cập nhật cùng một bản ghi bên ngoài.

## 12. Action-state, service và ranh giới transaction

Một flow có thể tồn tại vài phút hoặc lâu hơn trong khi người dùng lựa chọn. Không có lý do để giữ một database transaction mở suốt thời gian ấy.

~~~mermaid
flowchart LR
    C["contact: chờ nhập"] -->|next| P["package: chờ nhập"]
    P -->|next| R["review: chờ xác nhận"]
    R -->|confirm| A["submit service"]
    A -->|transaction ngắn| DB[("Database")]
    A --> E["completed"]
~~~

Ở mỗi view-state, người dùng có thể dừng lại bao lâu tùy ý trong giới hạn phiên. Chỉ ở action-state submit, service mới cần transaction để kiểm tra điều kiện và ghi đơn. Nếu xác nhận thất bại vì gói dịch vụ vừa hết hiệu lực, service trả về một **kết quả nghiệp vụ được nhận diện rõ**, flow chuyển đến state xử lý phù hợp.

**Exception kỹ thuật không tự biến thành event error.** Nếu flow cần nhánh lỗi có kiểm soát, service/adaptor phải chuyển kết quả nghiệp vụ thành outcome có chủ đích hoặc cấu hình xử lý exception rõ ràng. Với lỗi hạ tầng, cần log, thông báo phù hợp, khả năng retry có kiểm soát và tránh lộ chi tiết nội bộ.

Hủy một flow sau khi đã thực hiện các bước lưu bền vững có thể đòi hỏi **nghiệp vụ bù trừ**. Transition cancel chỉ biểu thị điều hướng, không thay thế transaction rollback hoặc cơ chế saga.

## 13. Tích hợp với Spring MVC ở mức request

Spring Web Flow thường phối hợp với những thành phần sau:

| Thành phần | Vai trò |
| --- | --- |
| **DispatcherServlet** | Điểm vào chung của các HTTP request trong Spring MVC |
| **FlowHandlerMapping** | Nhận diện request được ánh xạ đến flow |
| **FlowHandlerAdapter** | Kết nối việc xử lý request MVC với FlowExecutor |
| **FlowDefinitionRegistry** | Tìm định nghĩa flow theo ID |
| **FlowExecutor** | Khởi động, tiếp tục và kết thúc execution |
| **FlowExecutionRepository** | Quản lý việc lưu/khôi phục execution và continuation theo cấu hình |
| **ViewResolver / view engine** | Render trang ở view-state |
| **Service nghiệp vụ** | Validation cuối, quyền, transaction và thao tác ghi dữ liệu |

Sơ đồ trách nhiệm:

~~~mermaid
flowchart LR
    B["Browser"] --> MVC["Spring MVC"]
    MVC --> HM["FlowHandlerMapping / Adapter"]
    HM --> EX["FlowExecutor"]
    EX --> FD["FlowDefinitionRegistry"]
    EX --> REPO["FlowExecutionRepository"]
    EX --> V["View engine"]
    EX --> SV["Business services"]
~~~

Một ứng dụng có thể đồng thời có flow cho quy trình nhiều bước và controller MVC thông thường cho CRUD hoặc API đơn giản. Cấu hình tích hợp và khả năng tương thích phiên bản cần được kiểm tra với stack Spring Framework/Spring Boot đang dùng, nhất là ranh giới javax/jakarta trong các thế hệ thư viện khác nhau.

## 14. Bảo mật trạng thái qua nhiều request

Khóa execution giúp định vị ngữ cảnh flow; **không nên coi nó là cơ chế phân quyền độc lập**. Người dùng có thể sửa tham số request, gửi event bất kỳ hoặc gửi lại một khóa cũ.

Những biện pháp cần áp dụng:

- **Xác thực và phân quyền:** service và endpoint nhạy cảm phải xác minh quyền của người dùng đối với hành động, đối tượng dữ liệu và flow.
- **CSRF:** form thay đổi trạng thái cần bảo vệ CSRF theo cấu hình Spring Security. Không dùng execution key để thay thế CSRF token.
- **Giới hạn binding:** chỉ cho phép các property đã dự kiến; dữ liệu nhạy cảm như giá, quyền và trạng thái thanh toán phải được tính/kiểm tra tại server.
- **Chống submit trùng:** dùng requestId/idempotency và ràng buộc ở database.
- **Quản lý phiên:** bảo vệ session cookie, timeout, logout và xử lý request dùng execution đã hết hạn.
- **Bảo vệ dữ liệu:** chỉ lưu dữ liệu cần thiết trong scope; mã hóa và kiểm soát truy cập nơi dữ liệu bền vững được lưu.

Nếu trình duyệt gửi **_eventId=confirm** khi flow đang ở state contact nhưng state đó chỉ có event next/cancel, Web Flow không có transition confirm hợp lệ ở contact. Tuy nhiên, **giới hạn transition chưa phải là phân quyền nghiệp vụ**: mọi hành động ghi vẫn cần kiểm tra ở service.

## 15. Các trường hợp lỗi và cách phục hồi

| Tình huống | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Thiếu field bắt buộc | next không chuyển được sang bước sau | Giữ view hiện tại, hiển thị lỗi validation |
| Event không hợp lệ ở state hiện tại | Request không khớp transition | Không tự nhảy state; trả thông báo/hành vi lỗi có kiểm soát |
| Khóa execution cũ | Form được mở từ lịch sử trình duyệt | Kiểm tra khả năng restore snapshot; nếu không hợp lệ, yêu cầu tải lại |
| Session hết hạn | Không tìm được execution để tiếp tục | Thông báo hết phiên, cho khởi động lại hoặc phục hồi draft bền vững |
| Hai tab cùng gửi dữ liệu | Event dựa trên trạng thái khác nhau | Xử lý cạnh tranh và trạng thái cũ rõ ràng, kiểm tra ở tầng nghiệp vụ |
| Service không thể tạo đơn | Điều kiện nghiệp vụ đã thay đổi | Trả kết quả lỗi có ý nghĩa, cho người dùng chọn lại |
| Network retry sau khi đã commit | Người dùng không biết submit đã thành công | Truy vấn lại kết quả theo requestId, không tạo bản ghi trùng |
| Server restart hoặc failover | Execution không khôi phục được tùy repository/session | Thiết kế chiến lược session/repository và bản nháp bền vững phù hợp |

### 15.1. Phục hồi trải nghiệm khác với phục hồi transaction

Nếu form bị đóng, sản phẩm có thể khôi phục những trường đã nhập từ bản nháp database. Đó là **khôi phục trải nghiệm người dùng**. Nếu submit đã tạo đơn nhưng response thất lạc, cần tra cứu đơn đã tạo theo requestId để **phục hồi kết quả nghiệp vụ**.

Hai nhiệm vụ này khác nhau. Tạo một flow execution mới từ bản nháp không có nghĩa là giao dịch database trước đó chưa diễn ra.

## 16. Cách kiểm thử hành trình xuyên nhiều request

Để kiểm thử đúng, cần kiểm tra **cả state điều hướng lẫn dữ liệu giữ lại**. Ví dụ về ma trận kiểm thử:

| Kịch bản | Dữ liệu và event | Điều mong đợi |
| --- | --- | --- |
| Bắt đầu | GET /checkout | Execution mới, state contact |
| Nhập liên hệ hợp lệ | next + email hợp lệ | State package, draft.email được giữ |
| Quay lại | back từ package | State contact, email trước đó vẫn còn |
| Sửa email | next + email mới | State package, email mới thay email cũ |
| Bỏ trống email | next + email rỗng | State contact, có lỗi validation |
| Chọn gói | next + packageCode hợp lệ | State review, dữ liệu tổng hợp chính xác |
| Gửi event không được phép | confirm từ contact | Không thực hiện submit |
| Hủy | cancel từ state đang hoạt động | End-state cancelled |
| Xác nhận | confirm từ review | Service lưu, end-state completed |
| Gửi xác nhận lặp | Hai request cùng requestId | Không tạo hai đơn |
| Khóa đã hết hạn | Dùng khóa không thể khôi phục | Thông báo hết phiên/đường phục hồi phù hợp |

Một bản test theo ý tưởng có thể biểu diễn như sau:

~~~text
execution = startFlow("checkout")
assertState(execution, "contact")

execution = signal(execution, "next", { email: "an@example.com" })
assertState(execution, "package")
assertFlowData(execution, "draft.email", "an@example.com")

execution = signal(execution, "back")
assertState(execution, "contact")
assertFlowData(execution, "draft.email", "an@example.com")
~~~

Đây là **pseudocode**, không phải API Java có thể chạy nguyên văn. Một hệ thống hoàn chỉnh cần kiểm thử thêm tích hợp Spring MVC, render form, CSRF, validator, expiration, session serialization, concurrent requests và repository thực tế.

### 16.1. Những câu hỏi nên đặt khi một test lỗi

Nếu flow không đi tiếp sau next, trước hết hãy kiểm tra:

1. State hiện tại có transition cho event next hay không?
2. Request đã mang **execution key còn hiệu lực** và event đúng tên chưa?
3. Field được bind có nằm trong whitelist ở view-state không?
4. Binding/validation có chặn việc rời state không?
5. Service gọi trong transition/action có ném exception hoặc trả outcome không mong muốn không?
6. Session và repository có thực sự giữ được execution giữa các request không?

Các câu hỏi này giúp tách lỗi **đầu vào HTTP**, **trạng thái flow**, **validation** và **nghiệp vụ** thay vì sửa bừa các redirect trong controller.

## 17. Thực hành: truy vết một flow đặt lịch

Cho flow **booking** với các state: **chooseTime**, **contact**, **review**, **reserve** và **completed**. Người dùng mở trang chọn giờ lúc 09:00, nhập liên hệ lúc 09:02, xem lại lúc 09:03 và xác nhận lúc 09:05.

Yêu cầu:

1. Vẽ sequence diagram cho ba request: bắt đầu flow, nhấn next, nhấn confirm. Chỉ rõ khi nào phải lưu và khôi phục execution.
2. Định nghĩa các event hợp lệ ở mỗi view-state, bao gồm back và cancel.
3. Chọn scope cho thời gian đã chọn, email liên hệ, danh sách giờ trống và thông báo lỗi.
4. Giải thích vì sao không được giữ database transaction mở từ 09:00 đến 09:05.
5. Giả sử người khác đặt mất giờ đã chọn lúc 09:04: tại bước reserve hệ thống phải kiểm tra điều gì và hiển thị phản hồi như thế nào?
6. Giả sử session hết hạn lúc 09:04, hoặc người dùng bấm confirm hai lần: mô tả hai cách phục hồi khác nhau.

Một thiết kế đạt yêu cầu sẽ cho thấy rõ **request nào khởi động execution**, **request nào tiếp tục nó**, **dữ liệu gì tồn tại giữa các request**, và **kết quả nào cần được bảo vệ bằng transaction/idempotency tại service**.

## 18. Tổng kết và câu hỏi tự kiểm tra

Spring Web Flow giúp xây dựng một tương tác web **có trạng thái ở tầng ứng dụng**, dù từng HTTP request vẫn độc lập. **Flow definition** mô tả các state/event/transition; **flow execution** giữ bước hiện tại và dữ liệu của một lần thực hiện; **FlowExecutor** cùng repository phụ trách khởi tạo, tiếp tục và khôi phục execution theo cấu hình. **View-state** là điểm chờ người dùng, trong khi **action-state** thực hiện thao tác phía server.

Chọn scope phù hợp để giữ dữ liệu giữa các bước, quản lý execution key đúng cách và thiết kế trước kịch bản back, refresh, hết phiên, concurrent request, validation failure và submit lặp. Web Flow hỗ trợ điều hướng nhất quán; tính chính xác và an toàn của thao tác ghi dữ liệu vẫn phải do service và database bảo đảm.

**Tự kiểm tra:**

1. Vì sao một hành trình có trạng thái không cần giữ nguyên một HTTP request hay Java thread suốt quá trình?
2. HTTP session và flow execution khác nhau ở đâu? Một session có thể có nhiều execution không?
3. Khi một người từ contact đi sang package, những gì cần được lưu để request sau tiếp tục đúng?
4. Vì sao Back của trình duyệt có thể khác với event back do flow định nghĩa?
5. Nếu thấy event confirm được gửi từ state contact, tầng nào phải ngăn việc thực hiện submit?
6. Tại sao redirect sau POST không đủ để chống tạo đơn trùng?
7. Khi flow execution đã mất nhưng bản nháp có trong database, nên phục hồi theo nguyên tắc nào?
