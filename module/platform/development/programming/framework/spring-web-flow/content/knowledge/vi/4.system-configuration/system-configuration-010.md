# Phạm vi ApplicationContext chung và context của từng flow

## 1. Vì sao phải phân biệt hai loại context?

Trong Spring Web Flow (SWF), một ứng dụng web thường phục vụ nhiều người dùng, nhiều phiên trình duyệt và nhiều hành trình nghiệp vụ cùng lúc. Một người dùng có thể mở hai tab để tạo hai đơn hàng; nhiều người dùng có thể đồng thời đi qua cùng một flow đặt chỗ. Các hành trình đó cần dùng chung dịch vụ nghiệp vụ và cấu hình của ứng dụng, nhưng dữ liệu đang nhập của từng hành trình phải được giữ riêng.

Spring giải quyết hai nhu cầu ở hai lớp khác nhau:

- **Spring ApplicationContext** là container cấu hình và quản lý bean của ứng dụng. Nó cung cấp các dịch vụ dùng chung như service, repository, gateway, validator và các thành phần hạ tầng.
- **Context của flow** là trạng thái runtime của một lần thực thi flow. Nó giữ dữ liệu và tiến trình của một hành trình cụ thể, ví dụ bản nháp đơn hàng, lựa chọn hiện tại, dữ liệu biểu mẫu và trạng thái đang hoạt động.

Trong module **SPRING_WEB_FLOW**, mục tiêu là mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow. Việc phân định context giúp mỗi flow giữ đúng dữ liệu của nó, còn logic nghiệp vụ vẫn được cung cấp qua các bean dùng chung. Đây là nền tảng để tích hợp Spring MVC, binding và validation biểu mẫu, quản lý phiên, kiểm thử cũng như phục hồi khi luồng gặp lỗi.

Một quy tắc dễ nhớ: **ApplicationContext quản lý các thành phần của ứng dụng; flow context quản lý dữ liệu và tiến trình của một lần chạy flow.** Không nên dùng một bean singleton để lưu dữ liệu nhập của từng người dùng.

## 2. Spring ApplicationContext: container dùng chung

### 2.1. Vai trò và vòng đời

`ApplicationContext` là container trung tâm của Spring. Khi ứng dụng khởi động, container đọc cấu hình, tạo hoặc đăng ký bean, tiêm các dependency và quản lý vòng đời của chúng. Các flow có thể gọi những bean này thông qua cơ chế biểu thức và tích hợp của Spring Web Flow.

Ví dụ, một ứng dụng đặt hàng có thể có các bean:

- `orderService`: thực hiện quy tắc tạo, tính giá và xác nhận đơn hàng.
- `inventoryService`: kiểm tra tồn kho.
- `orderRepository`: đọc và ghi dữ liệu đơn hàng.
- `addressValidator`: kiểm tra địa chỉ giao hàng.
- `paymentGateway`: tích hợp với hệ thống thanh toán.

Các bean trên thường thuộc phạm vi singleton mặc định của Spring. Singleton có nghĩa là một instance cho một bean definition trong một `ApplicationContext`. Nó không có nghĩa là một instance duy nhất cho toàn bộ JVM: nếu ứng dụng tạo hai container độc lập, mỗi container có thể có instance riêng.

Bean singleton được chia sẻ giữa các request và flow truy cập cùng container. Vì vậy, bean dịch vụ thường nên giữ dependency và cấu hình ổn định, còn dữ liệu thay đổi theo người dùng nên được truyền qua tham số hoặc lưu trong kho trạng thái phù hợp.

Ví dụ về một dịch vụ không giữ dữ liệu của từng flow trong field:

~~~java
@Service
public class OrderService {

    public OrderDraft createDraft(String customerId) {
        OrderDraft draft = new OrderDraft();
        draft.setCustomerId(customerId);
        return draft;
    }

    public Quote calculateQuote(OrderDraft draft) {
        // Tính toán từ dữ liệu được truyền vào.
        return new Quote();
    }
}
~~~

`OrderService` có thể được nhiều flow gọi đồng thời. Mỗi lần gọi nhận bản nháp tương ứng qua tham số. Không nên thêm field như `private OrderDraft currentDraft;` vào service singleton rồi gán bản nháp hiện tại vào đó. Hai request có thể ghi đè dữ liệu của nhau, dẫn đến rò rỉ hoặc nhầm lẫn dữ liệu giữa người dùng.

### 2.2. Quan hệ root và child WebApplicationContext

Trong ứng dụng Spring MVC truyền thống, cấu hình web có thể tạo một cây `WebApplicationContext`:

- **Root WebApplicationContext** thường chứa service, repository, cấu hình dữ liệu và các thành phần dùng chung.
- **Child WebApplicationContext** do `DispatcherServlet` quản lý, thường chứa controller, view resolver và cấu hình MVC của servlet đó.

Child context nhìn thấy bean ở parent context. Chiều ngược lại không đúng: root context không tự nhìn thấy bean chỉ được khai báo trong child context. Nếu có nhiều `DispatcherServlet`, mỗi servlet có thể có child context riêng nhưng cùng kế thừa root context.

Cách bố trí này giúp các dịch vụ nghiệp vụ được chia sẻ, trong khi cấu hình trình bày và định tuyến có thể riêng theo servlet. Với Spring Web Flow, cần bảo đảm các thành phần tích hợp như flow handler mapping, flow handler adapter và cấu hình đăng ký flow nằm trong context mà `DispatcherServlet` xử lý request có thể truy cập.

Không bắt buộc mọi dự án phải có đúng hai context. Một ứng dụng nhỏ có thể dùng cấu hình đơn giản hơn. Điều quan trọng là hiểu bean được đăng ký ở container nào và thành phần nào cần truy cập bean đó.

### 2.3. Những gì nên và không nên đặt ở ApplicationContext

| Nên đặt trong ApplicationContext | Không nên dùng ApplicationContext để giữ |
| --- | --- |
| Service, repository, client tích hợp | Bản nháp biểu mẫu của một người dùng |
| Cấu hình, serializer, mapper | Bước hiện tại của một flow |
| Validator dùng chung, policy dùng chung | Lựa chọn tạm thời trong một wizard |
| Thành phần hạ tầng an toàn khi dùng đồng thời | Biến mutable đại diện cho người dùng hiện tại |

Singleton không đồng nghĩa với bất biến tuyệt đối. Một bean có thể sử dụng cache hoặc trạng thái kỹ thuật nếu cơ chế đó được thiết kế an toàn khi truy cập đồng thời. Tuy nhiên, dữ liệu nghiệp vụ riêng của một lần chạy flow không thuộc trách nhiệm của bean singleton.

## 3. Context runtime của Spring Web Flow

### 3.1. Flow definition và flow execution

Cần phân biệt hai khái niệm:

- **Flow definition** mô tả cấu trúc của hành trình: các state, event, transition, action, view-state và subflow. Định nghĩa thường được đăng ký trong `FlowRegistry` và được `FlowExecutor` sử dụng.
- **Flow execution** là một lần chạy cụ thể của flow definition. Nó có state hiện tại và dữ liệu runtime của chính lần chạy đó.

Một flow definition có thể được dùng để tạo nhiều flow execution. Ví dụ, định nghĩa `checkout` được nhiều khách hàng sử dụng đồng thời. Mỗi lần khách hàng bắt đầu checkout tạo một execution riêng, vì vậy bản nháp và tiến trình của khách hàng A không được trộn với khách hàng B.

Ở mỗi request, Spring Web Flow tạo hoặc khôi phục ngữ cảnh xử lý request. `RequestContext` cung cấp thông tin về flow execution hiện tại, event đang được xử lý, external context và các scope mà flow có thể truy cập. Đây là context của lần xử lý request trong Web Flow, không phải Spring `ApplicationContext`.

Có thể hình dung quan hệ như sau:

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Bean dùng chung: OrderService"]
    A --> C["FlowRegistry và FlowExecutor"]
    C --> D["Flow definition: checkout"]
    D --> E["Flow execution của khách hàng A"]
    D --> F["Flow execution của khách hàng B"]
    E --> G["RequestContext của request A"]
    F --> H["RequestContext của request B"]
    G --> I["Scope và state của flow A"]
    H --> J["Scope và state của flow B"]
~~~

Hai execution có thể gọi cùng `OrderService`, nhưng mỗi execution sở hữu trạng thái flow riêng. Đây là cách kết hợp cấu hình và dịch vụ dùng chung với trạng thái riêng cho từng hành trình.

### 3.2. Các scope của Spring Web Flow

Spring Web Flow cung cấp nhiều scope để xác định dữ liệu tồn tại trong bao lâu. Chọn scope dựa trên vòng đời nghiệp vụ của dữ liệu, không dựa trên việc biến đó tiện truy cập ở đâu.

| Scope | Vòng đời | Ví dụ phù hợp |
| --- | --- | --- |
| `requestScope` | Trong một HTTP request đang xử lý | Giá trị tạm chỉ cần cho request hiện tại |
| `flashScope` | Chuyển tiếp ngắn qua một transition tới view-state kế tiếp | Thông báo “đã lưu thành công” |
| `viewScope` | Trong thời gian flow ở cùng một view-state | Dữ liệu phụ trợ chỉ phục vụ màn hình hiện tại |
| `flowScope` | Từ khi flow bắt đầu đến khi flow kết thúc | Bản nháp đơn hàng trong một flow checkout |
| `conversationScope` | Trong thời gian conversation cấp cao nhất tồn tại; có thể dùng chung giữa flow cha và subflow | Mã tham chiếu hoặc dữ liệu cần được chia sẻ giữa các bước/subflow trong cùng hành trình |

`flowScope` là lựa chọn thường gặp cho dữ liệu nghiệp vụ tạm thời thuộc về một flow. Dữ liệu trong scope này được giữ qua các transition của flow, nhưng được giải phóng khi flow kết thúc.

`conversationScope` có phạm vi rộng hơn `flowScope`. Khi flow cha gọi subflow, subflow có flow scope riêng nhưng có thể truy cập conversation scope chung của conversation đó. Khi flow cấp cao nhất kết thúc, conversation kết thúc và dữ liệu thuộc conversation scope không còn cần thiết.

`flashScope` chỉ phù hợp cho dữ liệu chuyển tiếp ngắn. Không nên lưu một đối tượng nghiệp vụ quan trọng ở đó với kỳ vọng nó tồn tại xuyên suốt toàn bộ flow. Tương tự, `requestScope` không thích hợp để giữ dữ liệu qua nhiều bước vì mỗi lần người dùng gửi event có thể là một request khác.

### 3.3. Sơ đồ vòng đời scope

~~~mermaid
flowchart TD
    A["HTTP request bắt đầu"] --> B["requestScope"]
    B --> C["Xử lý event trong flow"]
    C --> D["Transition"]
    D --> E["flashScope chuyển thông tin ngắn hạn"]
    E --> F["View-state kế tiếp"]
    F --> G["viewScope của view-state"]
    C --> H["flowScope tồn tại qua các state"]
    H --> I["Flow kết thúc"]
    I --> J["flowScope được kết thúc"]
    H --> K["conversationScope tồn tại trong conversation"]
    K --> L["Flow cấp cao nhất kết thúc"]
    L --> M["conversationScope được kết thúc"]
~~~

Sơ đồ nhấn mạnh vòng đời tương đối. Một request có thể khôi phục execution đã tồn tại, xử lý event và kết thúc trong khi flow vẫn tiếp tục. Vì thế, request kết thúc không đồng nghĩa với flow kết thúc.

## 4. Cách ApplicationContext và flow scope phối hợp

Giả sử flow checkout có các bước nhập thông tin giao hàng, xem báo giá và xác nhận đơn hàng. Dịch vụ tạo bản nháp là bean dùng chung; bản nháp được tạo ra thuộc về flow execution hiện tại.

Ví dụ flow XML minh họa:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <var name="orderDraft" class="com.example.order.OrderDraft"/>

    <on-start>
        <evaluate
            expression="orderService.createDraft(customerId)"
            result="flowScope.orderDraft"/>
    </on-start>

    <view-state id="shipping" view="checkout/shipping">
        <transition on="continue" to="review"/>
    </view-state>

    <view-state id="review" view="checkout/review">
        <transition on="confirm" to="complete"/>
        <transition on="editShipping" to="shipping"/>
    </view-state>

    <end-state id="complete"/>
</flow>
~~~

Đây là ví dụ rút gọn để thể hiện ranh giới trách nhiệm; tên bean, dữ liệu đầu vào và view phải được điều chỉnh theo ứng dụng thực tế. `orderService` là bean do Spring quản lý và có thể được flow gọi. Kết quả `createDraft` được đặt vào `flowScope.orderDraft`, tức là bản nháp của execution hiện tại.

Khi một người dùng khác chạy cùng flow definition, Web Flow tạo execution khác và có `flowScope.orderDraft` riêng. Hai execution vẫn có thể dùng cùng một bean `orderService`.

Trong dự án thực tế, nên để service thực hiện quy tắc nghiệp vụ và truy cập dữ liệu bền vững. Flow định tuyến hành trình và điều phối lời gọi service. Tránh đưa toàn bộ quy tắc tính giá, kiểm tra quyền hoặc cập nhật cơ sở dữ liệu vào biểu thức điều hướng trong flow XML.

## 5. Phân chia dữ liệu giữa flow cha và subflow

Subflow giúp tách một phần hành trình có thể tái sử dụng, ví dụ flow chọn địa chỉ giao hàng hoặc flow xác nhận danh tính. Khi flow cha gọi subflow:

- Flow cha tiếp tục có flow scope của chính nó.
- Subflow có flow scope riêng trong thời gian nó chạy.
- Các flow trong cùng conversation có thể chia sẻ `conversationScope`.
- Khi subflow kết thúc, quyền điều khiển quay lại flow cha; dữ liệu chỉ thuộc flow scope của subflow không nên được xem là dữ liệu lâu dài của flow cha.

Hãy chọn cách trao đổi dữ liệu một cách rõ ràng. Dữ liệu đầu vào cho subflow có thể được truyền qua input mapping; kết quả trả về nên được ánh xạ qua output mapping hoặc cơ chế kết thúc subflow. Nếu dữ liệu cần được chia sẻ xuyên suốt conversation, dùng conversation scope có chủ đích.

Ví dụ về quyết định phạm vi:

| Dữ liệu | Vị trí phù hợp | Lý do |
| --- | --- | --- |
| Bản nháp checkout đang chỉnh sửa | `flowScope` của checkout | Chỉ thuộc hành trình checkout hiện tại |
| Kết quả tạm của subflow chọn địa chỉ | Output mapping về flow cha hoặc scope phù hợp | Flow cha cần nhận kết quả sau khi subflow kết thúc |
| Mã tham chiếu được dùng ở flow cha và subflow | `conversationScope` nếu đúng vòng đời | Hai flow trong cùng conversation cùng cần giá trị |
| Danh sách tỉnh/thành dùng chung | Service/cache hoặc dữ liệu ứng dụng | Không phụ thuộc một lần chạy flow |

Không nên dùng `conversationScope` chỉ vì muốn dữ liệu “sống lâu hơn”. Nếu dữ liệu là hồ sơ hoặc đơn hàng đã được xác nhận, nguồn sự thật nên là cơ sở dữ liệu hoặc dịch vụ nghiệp vụ. Scope của flow phù hợp với trạng thái điều phối tạm thời, không thay thế kho dữ liệu bền vững.

## 6. Context, HTTP session và lưu trạng thái flow

Một flow thường đi qua nhiều HTTP request. Khi người dùng chuyển từ màn hình này sang màn hình khác, Web Flow cần xác định execution nào đang tiếp tục và khôi phục trạng thái tương ứng. `FlowExecutor` phối hợp với repository của flow execution để quản lý việc bắt đầu, tiếp tục và kết thúc execution. Request tiếp tục flow thường mang thông tin định danh execution để hệ thống tìm đúng trạng thái.

Cần phân biệt ba khái niệm:

1. **HTTP session** là phiên phía máy chủ gắn với người dùng/trình duyệt theo cơ chế web.
2. **Flow execution** là một lần chạy cụ thể của flow, có thể tồn tại qua nhiều request.
3. **Conversation scope** là vùng dữ liệu thuộc một conversation của Web Flow, có thể bao gồm flow cha và các subflow.

Một HTTP session có thể chứa hoặc quản lý nhiều flow execution. Vì vậy, session scope của Spring và conversation scope của Web Flow không thể thay thế cho nhau. Một người dùng có thể mở nhiều tab, mỗi tab tiếp tục một execution khác nhau. Nếu đặt bản nháp hiện tại vào một bean session dùng chung, các tab có thể ghi đè dữ liệu của nhau.

Cơ chế lưu snapshot, repository và giới hạn số execution được giữ phụ thuộc cấu hình và phiên bản Web Flow. Khi triển khai, cần kiểm tra cấu hình repository đang dùng, chính sách hết hạn session, giới hạn tài nguyên và hành vi khi execution key không còn hợp lệ. Không nên giả định flow state tồn tại vô thời hạn.

Cũng cần cân nhắc nội dung được lưu trong flow state. Chỉ giữ dữ liệu tối thiểu cần thiết để tiếp tục hành trình. Không đưa mật khẩu, token bí mật hoặc thông tin xác thực nhạy cảm vào scope có thể được lưu hoặc tuần tự hóa. Dữ liệu lớn nên được lưu ở kho dữ liệu phù hợp và tham chiếu bằng ID.

## 7. Tích hợp với Spring MVC và vị trí đăng ký bean

Trong ứng dụng Spring MVC, request đi vào `DispatcherServlet`. Các thành phần tích hợp Web Flow giúp định tuyến request đến flow tương ứng và chuyển event đến execution đang hoạt động. Ở mức cấu hình, thường cần quan tâm:

- `FlowRegistry`: nơi đăng ký và tìm flow definition.
- `FlowExecutor`: điều phối bắt đầu, tiếp tục và kết thúc flow execution.
- Flow handler mapping: xác định request nào thuộc flow.
- Flow handler adapter: kết nối request của Spring MVC với flow executor.

Các thành phần này phải được cấu hình nhất quán và có thể truy cập từ luồng xử lý MVC. Các service nghiệp vụ dùng chung thường nằm trong root context; cấu hình MVC và thành phần web có thể nằm trong child context. Nếu flow không tìm thấy một bean, hãy kiểm tra bean đó được đăng ký ở context nào và context xử lý flow có nhìn thấy nó hay không.

Không nên khắc phục lỗi bean visibility bằng cách tạo một bản sao service tùy tiện trong từng flow. Trước hết hãy kiểm tra cây context, component scan và cấu hình dependency injection. Việc tạo nhiều instance có thể dẫn đến cấu hình không nhất quán hoặc nhiều kết nối tài nguyên ngoài ý muốn.

## 8. Kiểm thử ranh giới context và scope

Kiểm thử nên chứng minh cả hai mặt: dịch vụ dùng chung hoạt động đúng và dữ liệu của từng execution được cô lập.

### 8.1. Kiểm thử bean dùng chung

- Khởi tạo application context và xác nhận các service cần thiết được đăng ký.
- Xác nhận flow có thể gọi bean nghiệp vụ theo tên/biểu thức đã cấu hình.
- Kiểm tra service không giữ dữ liệu của request trước trong field mutable.
- Nếu có root và child context, kiểm tra child truy cập được bean ở root và cấu hình không phụ thuộc chiều truy cập ngược.

### 8.2. Kiểm thử nhiều flow execution

Tạo hai execution từ cùng một flow definition. Gán dữ liệu khác nhau vào flow scope của từng execution, thực hiện transition và xác nhận dữ liệu không bị trộn. Một tình huống hữu ích là hai bản nháp đơn hàng có customer ID khác nhau: sau khi cả hai cùng đi qua bước review, mỗi execution phải hiển thị đúng bản nháp của nó.

### 8.3. Kiểm thử subflow và kết thúc flow

- Kiểm tra flow cha truyền đúng input cho subflow.
- Kiểm tra subflow trả đúng output cho flow cha.
- Kiểm tra dữ liệu trong flow scope của subflow không bị coi là dữ liệu sống lâu sau khi subflow kết thúc.
- Kiểm tra dữ liệu conversation scope còn dùng được trong flow cha khi conversation vẫn tiếp tục.
- Kiểm tra kết thúc flow cấp cao nhất giải phóng trạng thái tạm theo vòng đời dự kiến.

Có thể dùng bộ hỗ trợ kiểm thử Spring Web Flow để chạy flow với external context giả lập, gửi event và kiểm tra state/scope. Với tích hợp HTTP thực tế, bổ sung kiểm thử Spring MVC để xác nhận handler mapping, adapter, session và view hoạt động cùng nhau.

## 9. Lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Hai người dùng nhìn thấy cùng dữ liệu biểu mẫu | Lưu dữ liệu theo người dùng trong field của singleton | Đưa dữ liệu vào flow scope của execution tương ứng |
| Hai tab ghi đè bản nháp của nhau | Dùng một session attribute làm trạng thái duy nhất | Mỗi tab tiếp tục execution riêng; dùng flow scope |
| Subflow không đọc được dữ liệu cần thiết | Chưa truyền input hoặc chọn scope sai | Khai báo input/output mapping hoặc dùng conversation scope đúng mục đích |
| Bean nghiệp vụ không được tìm thấy | Bean nằm trong context không được flow/MVC context nhìn thấy | Kiểm tra root-child hierarchy và vị trí đăng ký bean |
| Dữ liệu biến mất sau một transition | Đặt dữ liệu ở request hoặc flash scope trong khi cần sống lâu hơn | Chuyển sang view, flow hoặc conversation scope theo vòng đời |
| Dữ liệu tạm vẫn tồn tại sau khi hành trình hoàn tất | Dùng scope quá rộng hoặc không kết thúc flow đúng cách | Chọn scope hẹp nhất đáp ứng nghiệp vụ và kết thúc flow đúng thời điểm |
| Flow không tiếp tục được sau khi session hết hạn | Execution state hoặc key không còn khả dụng | Xử lý trường hợp execution hết hạn bằng thông báo và đường bắt đầu lại an toàn |

Khi điều tra lỗi, hãy lần lượt xác định: bean thuộc `ApplicationContext` nào, request đang tiếp tục execution nào, dữ liệu được ghi vào scope nào và vòng đời scope đó đã kết thúc hay chưa. Bốn câu hỏi này thường thu hẹp được nguyên nhân.

## 10. Quy trình chọn context cho một dữ liệu mới

Khi thêm một biến hoặc thành phần vào flow, có thể đi theo quy trình sau:

1. **Xác định bản chất dữ liệu.** Đây là dịch vụ/cấu hình dùng chung, dữ liệu tạm của một hành trình, hay dữ liệu bền vững của nghiệp vụ?
2. **Xác định người sở hữu.** Dữ liệu thuộc toàn ứng dụng, một flow execution, một conversation hay một request?
3. **Xác định vòng đời cần thiết.** Nó cần tồn tại trong một request, một view-state, toàn bộ flow hay qua flow cha và subflow?
4. **Chọn nơi lưu.** Bean dùng chung thuộc ApplicationContext; trạng thái điều phối tạm thuộc scope Web Flow; dữ liệu nghiệp vụ lâu dài thuộc kho dữ liệu.
5. **Kiểm tra truy cập đồng thời.** Nếu bean dùng chung, bảo đảm không có trạng thái người dùng mutable bị chia sẻ ngoài ý muốn.
6. **Viết kiểm thử cô lập.** Chạy ít nhất hai execution độc lập và kiểm tra transition, subflow, kết thúc flow.

Ví dụ: `OrderService` là bean singleton trong ApplicationContext; `orderDraft` thuộc `flowScope`; kết quả chọn địa chỉ từ subflow được trả về flow cha; đơn hàng đã xác nhận được lưu qua repository. Cách phân chia này làm rõ ai sở hữu dữ liệu và thời điểm dữ liệu cần được giải phóng.

## 11. Tự kiểm tra

Trước khi hoàn thành cấu hình, hãy tự trả lời các câu hỏi sau:

- Một bean singleton trong ApplicationContext có thể được nhiều flow execution gọi đồng thời không? Có. Vì vậy, bean không được dùng field mutable để giữ dữ liệu riêng của một execution.
- Hai flow execution từ cùng một flow definition có dùng chung `flowScope` không? Không. Mỗi execution có trạng thái flow riêng.
- Subflow có thể chia sẻ dữ liệu với flow cha bằng cách nào? Truyền input/output một cách tường minh hoặc dùng `conversationScope` khi dữ liệu thực sự thuộc cùng conversation.
- Dữ liệu chỉ cần trong request hiện tại nên nằm ở đâu? `requestScope`.
- Dữ liệu cần qua nhiều state của cùng flow nên nằm ở đâu? Thường là `flowScope`.
- `ApplicationContext` có thay thế cơ sở dữ liệu cho đơn hàng đã xác nhận không? Không. ApplicationContext quản lý bean; dữ liệu nghiệp vụ bền vững cần được lưu qua repository hoặc dịch vụ dữ liệu.

Khi ranh giới này rõ ràng, Spring Web Flow có thể đảm nhiệm việc điều phối state và transition, trong khi Spring ApplicationContext cung cấp các thành phần dùng chung. Kết quả là nhiều người dùng và nhiều hành trình có thể chạy đồng thời mà trạng thái của từng flow vẫn được cô lập và có vòng đời dễ kiểm soát.

