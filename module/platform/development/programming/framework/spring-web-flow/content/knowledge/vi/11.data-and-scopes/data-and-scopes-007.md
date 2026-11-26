# conversationScope và dữ liệu dùng chung giữa flow cha–con

Trong một quy trình nhiều bước, flow cha có thể gọi một hoặc nhiều subflow để xử lý phần việc chuyên biệt: thêm khách vào đơn đặt chỗ, xác minh địa chỉ, chọn phương thức thanh toán hoặc xác nhận thông tin giao hàng. Những flow này có thể cần đọc và cập nhật một số dữ liệu chung trong cùng một hành trình.

Spring Web Flow cung cấp **conversationScope** cho trường hợp đó. Scope này được tạo khi một **top-level flow** bắt đầu, được chia sẻ giữa flow cấp cao nhất và tất cả subflow thuộc conversation ấy, rồi bị hủy khi top-level flow kết thúc. Nhờ vậy, flow cha và flow con có thể dùng chung một ngữ cảnh hành trình mà không cần đưa mọi biến vào từng input/output mapping.

Tuy nhiên, conversationScope không phải kho dữ liệu dùng chung cho mọi flow trong cùng HTTP session. Mỗi top-level flow có conversation riêng; các flow con thuộc cùng cây hành trình mới chia sẻ conversation đó. Bài học này giải thích vòng đời, phạm vi nhìn thấy, cách phối hợp conversationScope với input/output mapping, và cách kiểm thử để dữ liệu không rò sang hành trình khác.

Bài thuộc chương **Dữ liệu và scope** của module **SPRING_WEB_FLOW**. Module giúp mô hình hóa hành trình web qua state, event, transition và subflow, đồng thời thực hành form binding, validation, quản lý scope/phiên, tích hợp Spring MVC và phục hồi lỗi. conversationScope là một phần trong thiết kế dữ liệu của hành trình: chọn đúng scope giúp flow cha–con phối hợp mà vẫn giữ ranh giới giữa những lần chạy độc lập.

## 1. Tình huống: flow cha gọi subflow để thêm khách

Giả sử người dùng tạo một booking. Flow cha quản lý toàn bộ hành trình:

~~~text
booking
  details
    ↓
  review
    ↓ addGuest
  createGuest (subflow)
    ↓ guestCreated
  review
    ↓ confirm
  confirmation
~~~

Flow cha sở hữu booking draft và quyết định khi nào hoàn tất. Subflow createGuest chỉ phụ trách nhập, xác thực và tạo một khách mới. Trong lúc thực hiện, cả hai flow có thể cần biết một số thông tin chung như:

- Mã hành trình đang xử lý.
- Locale đã chọn cho toàn bộ quy trình.
- Một mã correlation để ghi log các bước liên quan.
- Các bước con đã hoàn tất.
- Một số lựa chọn điều phối mà flow cha và flow con cùng sử dụng.

Nếu mỗi subflow phải nhận và trả lại tất cả thông tin điều phối, input/output mapping sẽ dài và khó duy trì. Nếu đưa tất cả vào một khóa HTTP session dùng chung, những hành trình độc lập của cùng người dùng có thể ghi đè dữ liệu của nhau.

conversationScope giải quyết đúng phạm vi ở giữa: **dùng chung trong một conversation top-level và các subflow của nó**.

~~~mermaid
flowchart TD
    S["HTTP session"] --> A["Top-level conversation A"]
    S --> B["Top-level conversation B"]
    A --> PA["Flow cha: booking A"]
    A --> CA["Subflow createGuest A"]
    A --> VA["Subflow verifyAddress A"]
    B --> PB["Flow cha: booking B"]
    B --> CB["Subflow createGuest B"]
    PA --- CA
    PA --- VA
    PB --- CB
    CA -. "cùng conversation A" .- VA
~~~

Flow A và B có thể chạy trong cùng HTTP session, nhưng mỗi top-level flow có conversation riêng. Subflow của A chia sẻ dữ liệu với A; subflow của B chia sẻ dữ liệu với B.

## 2. conversationScope là gì?

**conversationScope** là một trong các scope dữ liệu do Spring Web Flow quản lý. Theo reference guide:

- Scope được cấp phát khi một **top-level flow** bắt đầu.
- Scope được chia sẻ bởi top-level flow và tất cả subflow thuộc conversation đó.
- Scope bị hủy khi top-level flow kết thúc.
- Với implementation mặc định, dữ liệu conversation được lưu trong HTTP session; object lưu ở đây nên thường implement Serializable để hỗ trợ session replication.

Một biến có thể được đọc/ghi qua EL bằng cách chỉ rõ scope:

~~~xml
<set name="conversationScope.workflowId"
     value="'booking-journey-001'"/>
~~~

Hoặc lưu kết quả của expression:

~~~xml
<evaluate expression="journeyContextFactory.create()"
          result="conversationScope.journeyContext"/>
~~~

Tên thuộc tính sau dấu chấm là do ứng dụng đặt. Trong ví dụ, workflowId và journeyContext là dữ liệu của ứng dụng, còn conversationScope là scope của SWF.

### 2.1. Vòng đời theo top-level flow

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant P as Top-level flow
    participant C as Subflow
    participant S as conversationScope

    B->>P: Start flow
    P->>S: Allocate conversation
    P->>S: Set shared journey context
    P->>C: Start subflow
    C->>S: Read shared context
    C->>S: Update shared progress
    C-->>P: Return outcome
    P->>S: Read updated progress
    P->>C: Start another subflow
    C->>S: Read same conversation context
    C-->>P: Return outcome
    P->>S: Conversation remains available
    P-->>B: Top-level flow ends
    P->>S: Conversation is destroyed
~~~

Khi một subflow kết thúc, conversationScope **không bị hủy** nếu flow cha vẫn đang chạy. Flow cha có thể tiếp tục đọc dữ liệu mà subflow vừa cập nhật, rồi gọi một subflow khác trong cùng conversation.

Khi top-level flow kết thúc, conversationScope kết thúc theo. Không nên dựa vào nó để lưu thông tin cần tồn tại sau khi quy trình đã hoàn tất.

## 3. Phân biệt conversationScope với các scope còn lại

Mỗi scope có vòng đời và mục đích khác nhau. Chọn scope dựa trên câu hỏi: **dữ liệu cần tồn tại trong bao lâu và được những flow nào chia sẻ?**

| Scope | Vòng đời | Phạm vi sử dụng | Ví dụ |
|---|---|---|---|
| flowScope | Từ lúc một flow instance bắt đầu đến khi flow đó kết thúc | Một flow cụ thể | Draft riêng của flow cha hoặc subflow |
| viewScope | Từ khi vào một view-state đến khi rời state đó | Một view-state | Dữ liệu phụ trợ của một màn hình |
| requestScope | Trong lần flow invocation/request tương ứng | Xử lý tạm thời | Giá trị lấy từ request để dùng trong xử lý hiện tại |
| flashScope | Tạm thời qua một lần render; được làm sạch sau view render | Thông báo/ngữ cảnh ngắn hạn | Message sau một thao tác |
| conversationScope | Từ lúc top-level flow bắt đầu đến khi top-level flow kết thúc | Top-level flow và mọi subflow của nó | Journey context dùng chung cha–con |
| HTTP session attributes | Theo vòng đời HTTP session | Các request/flow dùng cùng session theo cơ chế ứng dụng | Tùy chọn giao diện hoặc thông tin phiên |

Điểm quan trọng là **flowScope của flow con không phải flowScope của flow cha**. Mỗi flow có phạm vi riêng. Nếu child flow cần nhận bookingId, hãy truyền input. Nếu cần trả Guest vừa tạo, hãy khai báo output. Nếu cả cây flow cần đọc/ghi một ngữ cảnh điều phối chung, conversationScope là lựa chọn phù hợp.

### 3.1. conversationScope không phải toàn bộ HTTP session

Với implementation mặc định, conversation-scoped objects được lưu trong HTTP session, nhưng điều đó không làm chúng trở thành dữ liệu session-wide. SWF vẫn gắn chúng với lifecycle của một conversation.

Ví dụ cùng một người dùng mở hai hành trình booking trong hai tab:

- Booking A có conversationScope A.
- Booking B có conversationScope B.
- Subflow createGuest A dùng conversationScope A.
- Subflow createGuest B dùng conversationScope B.

Không đặt một khóa như currentBookingDraft vào conversationScope với giả định mọi tab đều thấy cùng một giá trị. Hai top-level flows độc lập có conversation riêng.

### 3.2. Không nhầm với biến toàn cục

conversationScope cũng không phải static field, singleton bean hoặc cache toàn ứng dụng. Một singleton service được gọi từ nhiều request có thể phục vụ nhiều conversation, nhưng trạng thái mutable đặt trong field của singleton sẽ bị chia sẻ ngoài ý muốn.

Hãy đặt dữ liệu hành trình vào scope do SWF quản lý hoặc kho lưu trữ nghiệp vụ có khóa rõ ràng; service singleton nên nhận dữ liệu qua tham số.

## 4. Dữ liệu nào nên chia sẻ giữa flow cha và flow con?

Dữ liệu phù hợp với conversationScope thường có đặc điểm:

- Nhiều flow trong cùng một hành trình cần đọc hoặc cập nhật.
- Có vòng đời kết thúc khi top-level flow kết thúc.
- Không cần trở thành dữ liệu bền vững của nghiệp vụ.
- Không chứa resource runtime khó serialize.
- Có thể chia sẻ an toàn trong toàn bộ cây subflow.

Ví dụ:

| Dữ liệu | Nơi lưu phù hợp | Lý do |
|---|---|---|
| Correlation ID của hành trình | conversationScope | Cha và các subflow dùng chung khi ghi log |
| Locale được chọn cho toàn hành trình | conversationScope hoặc context phù hợp | Nhiều subflow cần cùng locale |
| Danh sách bước đã hoàn thành | conversationScope | Cha đọc tiến độ sau khi child kết thúc |
| Booking draft riêng của flow cha | flowScope của cha | Subflow không cần sở hữu toàn bộ draft |
| Form nhập Guest riêng của subflow | flowScope của child | Chỉ child quản lý form này |
| Lỗi hiển thị trong một view | viewScope hoặc message context | Chỉ phục vụ màn hình hiện tại |
| Message sau redirect | flashScope | Chỉ cần tồn tại ngắn hạn |
| Booking đã xác nhận | Database/service | Cần tồn tại sau khi conversation kết thúc |
| Entity manager, request/response, service bean | Không lưu trong conversationScope | Resource/runtime object không phù hợp với trạng thái flow được lưu |

Một quy tắc hữu ích: nếu dữ liệu cần tồn tại sau khi người dùng đóng tab, session hết hạn hoặc ứng dụng khởi động lại, hãy lưu vào database hoặc kho bền vững. conversationScope chỉ quản lý dữ liệu của hành trình đang chạy.

## 5. Khởi tạo context trong flow cha

Giả sử ứng dụng có DTO dùng chung:

~~~java
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class BookingJourneyContext implements Serializable {

    private static final long serialVersionUID = 1L;

    private String correlationId;
    private String locale;
    private List<String> completedTasks = new ArrayList<>();

    public String getCorrelationId() {
        return correlationId;
    }

    public void setCorrelationId(String correlationId) {
        this.correlationId = correlationId;
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }

    public List<String> getCompletedTasks() {
        return completedTasks;
    }

    public void setCompletedTasks(List<String> completedTasks) {
        this.completedTasks = completedTasks;
    }
}
~~~

Flow cha có thể tạo context khi bắt đầu:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <var name="booking"
         class="com.example.booking.BookingDraft"/>

    <on-start>
        <evaluate expression="bookingService.createDraft(currentUser.name)"
                  result="flowScope.booking"/>

        <evaluate expression="journeyContextFactory.create()"
                  result="conversationScope.journeyContext"/>
    </on-start>

    <view-state id="review"
                view="booking/review"
                model="booking">
        <transition on="addGuest" to="addGuest"/>
        <transition on="confirm" to="confirmation"/>
    </view-state>

    <!-- subflow-state được khai báo ở phần tiếp theo -->

</flow>
~~~

Ví dụ giả định các bean bookingService và journeyContextFactory đã được đăng ký. Context được tạo một lần khi top-level flow khởi động; các subflow được gọi sau đó có thể đọc cùng đối tượng qua conversationScope.

Không khởi tạo lại journeyContext trong mỗi subflow nếu mục tiêu là giữ tiến độ chung. Nếu child tự thay toàn bộ context bằng một object mới, flow cha sẽ nhìn thấy giá trị mới đó; cần xác định rõ flow nào được phép tạo hoặc thay thế context.

### 5.1. Dùng một object có namespace

Thay vì đặt hàng chục key rời rạc:

~~~text
conversationScope.locale
conversationScope.correlationId
conversationScope.lastTask
conversationScope.completedTasks
conversationScope.currentBooking
conversationScope.currentPayment
~~~

có thể gom dữ liệu điều phối vào một object có ý nghĩa:

~~~text
conversationScope.journeyContext
~~~

Cách này giúp tránh va chạm tên giữa các subflow, dễ kiểm tra kiểu dữ liệu và làm rõ phần nào thực sự là context chung.

## 6. Subflow đọc và cập nhật conversationScope

Flow cha gọi subflow createGuest. Nó truyền bookingId qua input mapping, trong khi context điều phối được chia sẻ trực tiếp bằng conversationScope.

Flow cha:

~~~xml
<subflow-state id="addGuest"
               subflow="createGuest">
    <input name="bookingId"
           value="flowScope.booking.id"/>

    <transition on="guestCreated"
                to="review">
        <evaluate expression="flowScope.booking.guests.add(currentEvent.attributes.guest)"/>
    </transition>

    <transition on="creationCancelled"
                to="review"/>
</subflow-state>
~~~

Flow con:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="
          http://www.springframework.org/schema/webflow
          http://www.springframework.org/schema/webflow/spring-webflow.xsd">

    <input name="bookingId"
           type="long"
           required="true"/>

    <var name="guest"
         class="com.example.booking.GuestDraft"/>

    <view-state id="details"
                view="guest/details"
                model="guest">
        <transition on="save" to="recordGuest"/>
        <transition on="cancel" to="cancelled"
                    bind="false"
                    validate="false"/>
    </view-state>

    <action-state id="recordGuest">
        <evaluate expression="guestService.createGuest(bookingId, guest)"
                  result="flowScope.savedGuest"/>

        <evaluate expression="journeyProgressAction.markCompleted(conversationScope.journeyContext, 'createGuest')"/>

        <transition to="guestCreated"/>
    </action-state>

    <end-state id="guestCreated">
        <output name="guest"
                value="flowScope.savedGuest"/>
    </end-state>

    <end-state id="cancelled"/>
</flow>
~~~

Đoạn XML minh họa input/output mapping và việc child có thể truy cập conversationScope. Ví dụ giả định guestService trả về Guest, journeyProgressAction cập nhật context và các bean đã được đăng ký trong Spring context. Chữ ký phương thức và cách đánh giá expression cần khớp với cấu hình SWF của dự án.

Action helper có thể được viết như sau:

~~~java
public class JourneyProgressAction {

    public void markCompleted(
            BookingJourneyContext context,
            String taskName) {

        if (!context.getCompletedTasks().contains(taskName)) {
            context.getCompletedTasks().add(taskName);
        }
    }
}
~~~

Sau khi subflow trả outcome guestCreated, flow cha có thể đọc:

~~~xml
<transition on="guestCreated" to="review">
    <evaluate expression="flowScope.booking.guests.add(currentEvent.attributes.guest)"/>
    <evaluate expression="bookingAuditService.recordCompletedTasks(conversationScope.journeyContext.completedTasks)"/>
</transition>
~~~

Điểm cần phân biệt:

- bookingId được truyền qua input contract và trở thành input của flow con.
- Guest được trả qua output attribute của end-state.
- journeyContext được đọc/ghi qua conversationScope vì nó thuộc phạm vi chia sẻ của cả conversation.
- guest draft và savedGuest thuộc flowScope của child, không tự động trở thành flowScope của parent.

## 7. conversationScope và input/output mapping: chọn cách nào?

Hai cơ chế có thể cùng xuất hiện trong một thiết kế nhưng giải quyết hai nhu cầu khác nhau.

**Input/output mapping** thể hiện contract giữa caller và callee. Flow cha nói rõ child cần dữ liệu gì và trả kết quả gì.

**conversationScope** cung cấp ngữ cảnh chung cho toàn bộ cây flow trong cùng top-level conversation. Nó phù hợp với dữ liệu điều phối được nhiều subflow dùng mà không cần lặp mapping ở mỗi lời gọi.

| Tiêu chí | Input/output mapping | conversationScope |
|---|---|---|
| Mục tiêu | Contract rõ giữa hai flow | Context chung trong một conversation |
| Dữ liệu vào child | Khai báo input | Child đọc shared context |
| Dữ liệu trả về | Output của end-state | Child cập nhật context chung |
| Phạm vi | Cặp caller/callee | Top-level flow và mọi subflow |
| Khả năng đọc code | Rõ ràng, dễ thấy phụ thuộc | Cần biết key nào đang dùng chung |
| Coupling | Contract tường minh | Các flow phụ thuộc cấu trúc context |
| Thích hợp | bookingId, Guest, kết quả xác minh | correlationId, locale, tiến độ chung |

### 7.1. Ưu tiên contract tường minh cho dữ liệu nghiệp vụ

Nếu child cần một bookingId, hãy truyền bookingId qua input thay vì buộc child biết cấu trúc của một object context lớn.

Nếu child tạo một Guest, hãy trả Guest qua output thay vì để parent đọc một key chung không rõ ai sở hữu.

conversationScope nên giữ dữ liệu thực sự cần được chia sẻ rộng trong cây flow, ví dụ correlation ID hoặc tiến độ. Đừng biến nó thành túi chứa tất cả biến vì như vậy mọi flow con sẽ phụ thuộc lẫn nhau.

### 7.2. Không truyền cả entity nếu chỉ cần một ID

Một child flow chỉ cần tra cứu booking có thể nhận bookingId thay vì nhận toàn bộ entity. Service sẽ tải lại bản ghi và kiểm tra quyền. Điều này giảm coupling và tránh giữ object lớn trong flow state.

Nếu dùng conversationScope để chia sẻ object mutable, mọi flow con có thể thay đổi object đó. Hãy giới hạn quyền sửa bằng API/service rõ ràng và tránh để nhiều subflow cùng cập nhật các phần dữ liệu chồng lấn.

## 8. Nhiều cấp subflow vẫn dùng cùng conversation

Một flow cha có thể gọi child, child lại gọi grandchild:

~~~text
booking (top-level)
  └── addGuest (subflow)
        └── verifyGuestIdentity (subflow)
~~~

Cả ba flow thuộc cùng một conversation. Do đó:

- booking có flowScope riêng.
- addGuest có flowScope riêng.
- verifyGuestIdentity có flowScope riêng.
- Cả ba cùng nhìn thấy conversationScope của top-level booking.

~~~mermaid
flowchart TD
    C["conversationScope của booking"] --> P["Flow booking"]
    C --> A["Subflow addGuest"]
    C --> V["Subflow verifyGuestIdentity"]
    P --> PF["flowScope booking"]
    A --> AF["flowScope addGuest"]
    V --> VF["flowScope verifyGuestIdentity"]
~~~

Nếu verifyGuestIdentity cập nhật một trường chung trong journeyContext, addGuest và booking có thể đọc giá trị mới sau khi flow con trả về. Nhưng flowScope của verifyGuestIdentity vẫn kết thúc theo lifecycle của child; biến cục bộ của child không tự động được copy vào flowScope của cha.

### 8.1. Kết thúc child không kết thúc conversation

End-state của child trả outcome cho parent. Parent tiếp tục tại transition tương ứng. conversationScope vẫn tồn tại cho đến khi top-level flow đi tới end-state.

Đây là lý do không nên xóa toàn bộ journeyContext trong on-end của mỗi child. Nếu child dọn context chung khi kết thúc, các subflow tiếp theo hoặc flow cha có thể mất dữ liệu.

### 8.2. Khi child bị hủy

Nếu child kết thúc bằng outcome cancelled, parent nhận event đó và quyết định tiếp tục, cho sửa lại hoặc hủy toàn bộ hành trình. conversationScope vẫn thuộc parent. Nếu cần đánh dấu một tác vụ bị hủy, hãy cập nhật trạng thái cụ thể thay vì xóa context chung.

## 9. Nhiều top-level flow trong cùng HTTP session

Giả sử người dùng mở hai tab và bắt đầu hai booking mới. Cả hai request dùng cùng cookie HTTP session, nhưng mỗi lần launch top-level flow tạo một conversation riêng.

~~~mermaid
flowchart TD
    H["HTTP session của người dùng"] --> A["Conversation A"]
    H --> B["Conversation B"]
    A --> A1["booking A flowScope"]
    A --> A2["createGuest A"]
    A --> AC["conversationScope A"]
    B --> B1["booking B flowScope"]
    B --> B2["createGuest B"]
    B --> BC["conversationScope B"]
~~~

Không có quan hệ chia sẻ giữa conversationScope A và B. Child của A không thể dùng conversationScope để đọc context của B.

Đây là điểm khác biệt với một attribute lưu trực tiếp trong HTTP session: session attribute có thể được nhiều conversation cùng đọc/ghi nếu ứng dụng dùng chung key. conversationScope được SWF quản lý theo từng conversation.

### 9.1. Đừng dùng conversationScope làm bộ nhớ giỏ hàng toàn tài khoản

Nếu yêu cầu nghiệp vụ là người dùng có một giỏ hàng duy nhất xuyên nhiều tab, nhiều phiên hoặc nhiều thiết bị, đó là dữ liệu bền vững của ứng dụng. Hãy lưu giỏ hàng trong database/cache có định danh người dùng và quyền truy cập phù hợp.

conversationScope chỉ tồn tại trong một hành trình top-level flow đang chạy; nó không đáp ứng yêu cầu chia sẻ toàn tài khoản.

## 10. Serialization, session replication và dữ liệu lớn

Theo implementation mặc định, conversation-scoped objects được lưu trong HTTP session. SWF cần lưu trạng thái execution giữa các request; môi trường có session replication hoặc distributed session thường cần các object tương thích serialization.

Một DTO dùng trong conversation nên:

- Implement Serializable.
- Chứa kiểu dữ liệu đơn giản hoặc object cũng serialize được.
- Tránh giữ reference tới ServletRequest/Response, stream, connection, EntityManager hoặc resource mở.
- Tránh giữ toàn bộ entity graph lớn.
- Tránh lưu dữ liệu nhạy cảm không cần thiết.
- Có kích thước nhỏ và vòng đời ngắn.

Ví dụ không nên lưu:

~~~java
public class BadJourneyContext implements Serializable {
    private HttpServletRequest request;
    private EntityManager entityManager;
    private DataSource dataSource;
}
~~~

Các field này là resource runtime, không phù hợp để lưu vào conversation state. Hãy lưu một correlation ID, booking ID hoặc DTO nhỏ, rồi service lấy lại resource khi cần.

### 10.1. Entity có Serializable vẫn chưa chắc phù hợp

Một entity implement Serializable không có nghĩa nên đưa cả entity graph vào conversationScope. Entity có thể kéo theo lazy proxy, collection lớn, quan hệ vòng hoặc dữ liệu thay đổi ngoài execution. Khi resume, object có thể stale hoặc khó tương thích với phiên bản ứng dụng mới.

Thông thường nên lưu **ID và dữ liệu form cần thiết** trong flow state, còn service tải entity mới trong transaction và kiểm tra quyền trước khi thao tác.

### 10.2. Session replication và rolling deployment

Nếu session được replicate giữa các node, object conversation phải serialize được trên node nguồn và deserialize được trên node đích. Khi deploy phiên bản mới, thay đổi class DTO có thể làm session cũ không còn tương thích.

Cần cân nhắc:

- Versioning DTO và serialVersionUID.
- Thời gian sống tối đa của flow/conversation.
- Chiến lược invalidate session hoặc xử lý execution cũ khi deploy.
- Kích thước dữ liệu session.
- Sticky session hoặc distributed session repository theo kiến trúc triển khai.

Không coi conversationScope là kho lưu trữ lâu dài qua mọi lần deploy.

## 11. Mutable shared context và request đồng thời

Vì flow cha và các subflow cùng truy cập một conversationScope, một object mutable trong đó có thể được nhiều flow sửa. Điều này hữu ích nhưng cũng tạo coupling và rủi ro race condition nếu có request đồng thời.

Ví dụ:

~~~java
context.getCompletedTasks().add("createGuest");
context.getCompletedTasks().add("verifyAddress");
~~~

Nếu hai thao tác cập nhật cùng diễn ra đồng thời, collection không thread-safe có thể gặp lost update hoặc lỗi dữ liệu tùy cách repository/ứng dụng xử lý request.

Các nguyên tắc:

1. Ưu tiên cập nhật conversation theo từng bước tuần tự của flow.
2. Dùng action/service helper thay vì cho mọi view tự sửa context.
3. Tránh hai subflow cùng sửa một cấu trúc mutable trong cùng thời điểm.
4. Nếu có xử lý bất đồng bộ, dùng cơ chế đồng bộ hoặc persistence có transaction phù hợp.
5. Không giả định flow execution repository và conversation object tự cung cấp mọi bảo đảm concurrency mà ứng dụng cần.

### 11.1. Nhân bản tab không tạo conversation mới nếu resume cùng execution

Nếu người dùng nhân bản URL chứa execution key của cùng một flow, hai tab có thể cùng tiếp tục một execution/conversation hoặc các snapshot liên quan. Chúng không tự có conversationScope độc lập chỉ vì là hai tab.

Muốn có hành trình độc lập, hãy launch top-level flow mới. Khi đó SWF tạo conversation mới theo lifecycle của flow.

### 11.2. Đừng lưu trạng thái authorization vào context như bằng chứng lâu dài

Có thể lưu role snapshot hoặc kết quả kiểm tra quyền để hiển thị UI, nhưng service phải kiểm tra lại quyền trước side effect. Quyền có thể bị thu hồi, booking có thể đổi owner hoặc tenant. conversationScope không phải ranh giới bảo mật.

## 12. Kết hợp conversationScope với lifecycle hooks

Flow definition có thể khởi tạo context ở on-start và cập nhật/đóng gói dữ liệu khi hoàn tất.

Ví dụ:

~~~xml
<on-start>
    <evaluate expression="journeyContextFactory.create()"
              result="conversationScope.journeyContext"/>
</on-start>
~~~

Subflow cập nhật tiến độ:

~~~xml
<action-state id="recordCompletion">
    <evaluate expression="journeyProgressAction.markCompleted(conversationScope.journeyContext, 'verifyAddress')"/>
    <transition to="verified"/>
</action-state>
~~~

Top-level flow có thể ghi kết quả tổng kết trước khi kết thúc:

~~~xml
<end-state id="completed">
    <on-entry>
        <evaluate expression="bookingAuditService.recordJourneySummary(conversationScope.journeyContext)"/>
    </on-entry>
</end-state>
~~~

Ví dụ end-state chỉ minh họa vị trí gọi audit. Nếu cần bảo đảm audit và dữ liệu nghiệp vụ cùng commit, hãy đặt chúng trong transaction service phù hợp; không dựa vào lifecycle hook để thay thế transaction coordination.

### 12.1. Dọn dữ liệu ở đúng cấp

Nếu child chỉ hoàn thành một phần công việc, không xóa conversationScope. Nếu top-level flow kết thúc, SWF quản lý lifecycle và hủy conversation. Không cần tự xóa từng key chỉ để giải phóng scope, trừ khi ứng dụng có lý do cụ thể cần loại bỏ dữ liệu nhạy cảm sớm hơn.

Nếu cần xóa một phần context trước khi kết thúc, hãy thực hiện qua service/action có chủ đích và test các nhánh cancel/error.

## 13. Kiểm thử chia sẻ dữ liệu cha–con

Một test chỉ gọi method service và xác nhận object thay đổi chưa chứng minh conversationScope hoạt động. Cần chạy flow cha, gọi subflow và quan sát dữ liệu ở cả hai phía.

### 13.1. Kịch bản cơ bản

| Bước | Thao tác | Kỳ vọng |
|---|---|---|
| 1 | Start top-level booking | Tạo conversationScope A |
| 2 | Flow cha đặt journeyContext | Parent đọc được context |
| 3 | Parent gọi createGuest | Child bắt đầu trong conversation A |
| 4 | Child đọc journeyContext | Nhận đúng context do parent tạo |
| 5 | Child cập nhật completedTasks | Context chung phản ánh tác vụ |
| 6 | Child trả guestCreated và output guest | Parent nhận event và output |
| 7 | Parent đọc journeyContext | Thấy cập nhật từ child |
| 8 | Parent gọi verifyAddress | Subflow thứ hai đọc cùng context |
| 9 | Parent kết thúc | Conversation A bị hủy theo lifecycle |

### 13.2. Flow execution test

Dùng flow execution test support của phiên bản SWF đang dùng để nạp flow cha và subflow thực tế. Không chỉ gọi setter của DTO rồi kết luận scope đã chia sẻ đúng.

Test nên xác minh:

- Parent tạo context trước khi gọi child.
- Child đọc đúng context do parent tạo.
- Child cập nhật context và parent thấy thay đổi sau outcome.
- Child flowScope vẫn độc lập với parent flowScope.
- Output của child xuất hiện trong current event của transition bên cha.
- Kết thúc child không kết thúc conversation.
- Kết thúc top-level flow mới kết thúc conversation.

Tên helper và API truy cập FlowSession phụ thuộc test support của phiên bản; dùng harness như AbstractXmlFlowExecutionTests hoặc integration test phù hợp với cấu hình thật thay vì dựa vào một MockFlowSession giả định.

### 13.3. Test hai conversation độc lập trong cùng session

Một test quan trọng khác:

1. Tạo một HTTP session.
2. Start top-level flow A.
3. Start top-level flow B từ entry URL mới, vẫn dùng cùng session.
4. Đặt context A là journey-A, context B là journey-B.
5. Gọi child của A và child của B.
6. Xác nhận child A đọc journey-A, child B đọc journey-B.
7. Cập nhật context trong A; xác nhận B không thay đổi.
8. Kết thúc A; xác nhận B vẫn tiếp tục nếu execution/session của B còn hợp lệ.

Không dùng hai MockHttpSession khác nhau cho test này; cần cùng session để chứng minh conversation isolation.

### 13.4. Test serialization

Nếu môi trường production replicate session:

- Serialize context DTO và deserialize lại.
- Kiểm tra collection, nested DTO và custom type.
- Kiểm tra dữ liệu không giữ reference tới resource runtime.
- Thử khôi phục session trên node khác nếu deployment hỗ trợ.
- Kiểm tra session cũ khi rolling deployment nếu có yêu cầu tương thích.

## 14. Lỗi thường gặp và cách xử lý

### 14.1. Child không nhìn thấy dữ liệu cha đã đặt trong flowScope

**Nguyên nhân:** flowScope là phạm vi riêng của mỗi flow. Child không tự động kế thừa flowScope của parent.

**Cách xử lý:** truyền dữ liệu cần thiết qua input hoặc đặt context chung vào conversationScope nếu nhiều subflow thật sự cần dùng.

### 14.2. Parent không thấy biến local của child sau khi child kết thúc

**Nguyên nhân:** child flowScope kết thúc cùng child. Biến local không tự động được chuyển vào parent.

**Cách xử lý:** khai báo output trong end-state của child và đọc qua currentEvent.attributes, hoặc cập nhật conversationScope nếu đó là dữ liệu chung.

### 14.3. Child thay đổi conversationScope nhưng parent không thấy

Kiểm tra:

- Parent và child có thật sự thuộc cùng top-level conversation không?
- Child có ghi đúng key conversationScope không?
- Code có tạo một context mới ở child thay vì sửa context hiện tại không?
- Child có đang chạy như top-level flow độc lập thay vì subflow không?
- Thay đổi có được ghi trước khi child trả outcome không?

### 14.4. Dữ liệu bị mất sau khi child kết thúc

Có thể ứng dụng đang lưu dữ liệu ở child flowScope hoặc viewScope rồi mong nó sống sau end-state. Hãy chuyển dữ liệu cần dùng tiếp sang output hoặc conversationScope trước khi child kết thúc.

### 14.5. Dữ liệu bị chia sẻ giữa hai tab ngoài ý muốn

Có thể code đã dùng HTTP session attribute hoặc singleton mutable field thay vì conversationScope, hoặc hai tab thực tế resume cùng execution key.

Kiểm tra cách launch flow, execution URL, nơi đọc/ghi context và bean singleton. Hai top-level flows được launch riêng phải có conversation riêng.

### 14.6. Session serialization thất bại

Nguyên nhân thường là context chứa object không serializable hoặc giữ resource runtime. Dùng DTO nhỏ, ID và kiểu dữ liệu đơn giản; không lưu request, response, connection hay entity manager.

### 14.7. Context tăng kích thước qua mỗi subflow

Nếu mỗi child thêm toàn bộ request, entity hoặc lịch sử vào conversationScope, session có thể phình lớn. Chỉ giữ dữ liệu điều phối cần thiết; lưu lịch sử nghiệp vụ ở database.

### 14.8. Subflow ghi đè key chung

Nhiều child có thể cùng dùng tên như status, result hoặc currentItem. Dùng một DTO có namespace rõ ràng và đặt tên thuộc tính theo ý nghĩa, ví dụ journeyContext.addressVerificationStatus.

## 15. Bài tập thực hành: dùng chung context trong quy trình đặt lịch

Tạo top-level flow booking và hai subflow createGuest, verifyAddress.

**Flow cha cần:**

- Tạo booking draft trong flowScope.
- Tạo journeyContext trong conversationScope.
- Gọi createGuest và truyền bookingId qua input.
- Nhận Guest qua output của end-state.
- Đọc tiến độ mà child đã ghi vào journeyContext.
- Gọi verifyAddress trong cùng conversation.
- Kết thúc top-level flow sau khi xác nhận.

**Subflow createGuest cần:**

- Nhận bookingId bằng input.
- Giữ guest form trong flowScope riêng.
- Tạo Guest qua service.
- Cập nhật completedTasks trong conversationScope.
- Trả Guest bằng output attribute.
- Không xóa conversation context khi child kết thúc.

**Subflow verifyAddress cần:**

- Đọc correlationId và locale từ conversationScope.
- Nhận address hoặc bookingId qua input theo contract rõ ràng.
- Trả outcome verified hoặc rejected.
- Cập nhật trạng thái xác minh trong journeyContext.

**Bài kiểm thử:**

1. Xác nhận parent và child đọc cùng journeyContext.
2. Xác nhận flowScope của child không chứa booking draft của parent nếu không truyền input.
3. Xác nhận parent nhận Guest qua output.
4. Xác nhận child kết thúc nhưng conversation vẫn tồn tại.
5. Xác nhận hai top-level flows cùng HTTP session không chia sẻ context.
6. Xác nhận kết thúc top-level flow làm conversation kết thúc.
7. Kiểm tra serialization của context.
8. Thử child bị cancel và xác nhận parent vẫn có thể tiếp tục theo outcome.
9. Thử session timeout và xác nhận không coi conversation là dữ liệu bền vững.
10. Xác nhận service vẫn kiểm tra quyền và trạng thái booking trước khi ghi.

### Câu hỏi tự kiểm tra

**1. conversationScope được tạo và hủy khi nào?** Được tạo khi top-level flow bắt đầu và bị hủy khi top-level flow kết thúc.

**2. Những flow nào chia sẻ conversationScope?** Top-level flow và tất cả subflow thuộc conversation của nó, kể cả subflow lồng nhau.

**3. Hai top-level flows trong cùng HTTP session có cùng conversationScope không?** Không. Mỗi top-level flow có conversation riêng.

**4. flowScope của child có phải flowScope của parent không?** Không. Mỗi flow instance có flowScope riêng.

**5. Khi nào nên dùng input/output mapping thay vì conversationScope?** Khi dữ liệu là đầu vào hoặc kết quả cụ thể của một lời gọi flow; contract tường minh giúp giảm coupling.

**6. Vì sao không nên lưu toàn bộ entity graph trong conversationScope?** Vì dữ liệu flow có thể được lưu qua session/repository, object lớn hoặc proxy khó serialize và có thể stale.

**7. Child kết thúc có làm conversation kết thúc không?** Không, nếu parent còn chạy. Conversation chỉ kết thúc khi top-level flow kết thúc.

**8. conversationScope có phải kho lưu dữ liệu bền vững không?** Không. Nó phục vụ hành trình đang chạy; dữ liệu cần tồn tại lâu dài phải được lưu ở tầng nghiệp vụ.

**9. Vì sao cần kiểm tra hai conversation trong cùng HTTP session?** Để chứng minh phạm vi conversation tách biệt ngay cả khi cookie/session được chia sẻ.

## 16. Checklist trước khi triển khai

- [ ] Đã xác định top-level flow tạo conversation.
- [ ] Đã xác định subflow nào thuộc cùng conversation.
- [ ] Dữ liệu cần chia sẻ thực sự nằm trong conversationScope.
- [ ] Draft riêng của từng flow vẫn nằm trong flowScope phù hợp.
- [ ] Dữ liệu vào child được truyền qua input mapping.
- [ ] Kết quả child được trả qua output/end-state.
- [ ] Không dùng conversationScope làm túi chứa mọi biến của ứng dụng.
- [ ] Context có namespace và kiểu dữ liệu rõ ràng.
- [ ] DTO lưu trong conversation tương thích serialization theo repository/session deployment.
- [ ] Không lưu servlet request/response, connection, EntityManager hoặc resource runtime.
- [ ] Không lưu entity graph lớn hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Không nhầm conversationScope với HTTP session attribute.
- [ ] Không dùng conversationScope để chia sẻ dữ liệu giữa các top-level flows độc lập.
- [ ] Không dùng scope làm bằng chứng authorization.
- [ ] Cập nhật mutable context theo cách có kiểm soát; xem xét request đồng thời.
- [ ] Child cancel/end không xóa context chung khi parent còn chạy.
- [ ] Có test parent-child sharing, flowScope isolation và hai conversations trong cùng session.
- [ ] Có test serialization/session replication nếu môi trường yêu cầu.
- [ ] Dữ liệu cần tồn tại sau top-level flow được lưu vào persistence layer.

**Ghi nhớ:** conversationScope được tạo theo **top-level flow**, chia sẻ cho flow cha và toàn bộ subflow, rồi kết thúc cùng top-level flow. flowScope vẫn riêng cho từng flow instance; input/output mapping là contract rõ ràng để truyền dữ liệu giữa caller và child. Hãy dùng conversationScope cho context điều phối chung, giữ draft riêng trong flowScope, và lưu dữ liệu nghiệp vụ dài hạn ở service/database. Như vậy, các flow con có thể phối hợp mà không làm lẫn những hành trình độc lập của cùng người dùng.

### Tài liệu tham khảo

- [Spring Web Flow 2.5.1 Reference — Variable Scopes and Calling Subflows](https://docs.spring.io/spring-webflow/docs/2.5.1.RELEASE/reference/html/defining-flows.html)
- [Spring Web Flow 2.5.x Reference — Defining Flows](https://docs.spring.io/spring-webflow/docs/2.5.x/reference/html/defining-flows.html)
- [Spring Web Flow 3.0 Reference — Defining Flows](https://docs.spring.io/spring-webflow/docs/3.0.x/reference/)

