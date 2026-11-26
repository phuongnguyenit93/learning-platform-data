# Kiểm thử flow cha với subflow giả

## 1. Vì sao cần kiểm thử flow cha độc lập với subflow?

Trong Spring Web Flow, flow cha có thể gọi một subflow để thực hiện một phần hành trình có thể tái sử dụng, chẳng hạn chọn địa chỉ, xác minh khách hàng hoặc chọn phương thức thanh toán. Khi subflow kết thúc, flow cha nhận event kết thúc và tiếp tục theo transition tương ứng. Nếu kiểm thử flow cha bằng toàn bộ subflow thật, một lỗi ở bên trong subflow có thể làm bài kiểm thử flow cha thất bại dù logic điều phối của flow cha vẫn đúng.

Dùng **subflow giả** giúp kiểm thử ranh giới tích hợp một cách có kiểm soát. Thay vì chạy toàn bộ nghiệp vụ con, test đăng ký một flow thay thế có cùng định danh và hợp đồng mà flow cha mong đợi. Flow thay thế có thể kết thúc ngay với event `selected`, `cancelled` hoặc một kết quả đã định trước.

Cách làm này giúp trả lời các câu hỏi quan trọng:

- Flow cha có truyền đúng input cho subflow không?
- Flow cha có nhận đúng event kết thúc và chọn đúng transition không?
- Nếu subflow trả về dữ liệu, flow cha có nhận và sử dụng đúng output không?
- Nhánh hủy hoặc kết quả khác có được xử lý đúng không?
- Flow cha có giữ dữ liệu và state của nó sau khi subflow kết thúc không?

Bài học này thuộc chương **Subflow và tái sử dụng** của module **SPRING_WEB_FLOW**. Với những hành trình nhiều bước được mô hình hóa bằng state, event, transition và subflow, kiểm thử flow cha với subflow giả giúp tách trách nhiệm, giảm phụ thuộc giữa các bài kiểm thử và phát hiện sớm lỗi ở hợp đồng tích hợp.

## 2. Phân biệt stub subflow, mock service và subflow thật

Có ba cách kiểm thử thường gặp, mỗi cách có mục tiêu riêng:

| Cách kiểm thử | Thành phần được thay thế | Mục tiêu |
| --- | --- | --- |
| Subflow giả (stub flow) | Flow definition được gọi bởi flow cha | Kiểm tra điều phối, input/output và event kết thúc của flow cha |
| Mock service trong subflow | Service mà subflow gọi | Kiểm tra logic của subflow mà không gọi hệ thống bên ngoài |
| Subflow thật | Không thay thế flow con | Kiểm tra tích hợp end-to-end giữa flow cha và flow con |

Trong bài này, trọng tâm là stub flow. Đây là một flow definition nhỏ, đăng ký trong test registry dưới đúng ID mà flow cha dùng. Stub giữ hợp đồng bên ngoài giống subflow thật nhưng có phần thực thi tối giản và kết quả xác định.

Ví dụ, flow cha gọi `address/select`. Trong môi trường kiểm thử, registry có thể ánh xạ ID đó tới một flow fixture kết thúc ngay bằng event `selected`. Khi chạy ứng dụng thật, registry production ánh xạ cùng ID tới flow chọn địa chỉ đầy đủ.

Không nên nhầm stub flow với việc mock trực tiếp `FlowExecutor` hoặc bỏ qua cơ chế subflow. Mục tiêu của bài kiểm thử là xác nhận Spring Web Flow thực sự khởi chạy subflow theo registry, truyền dữ liệu và xử lý event kết thúc. Vì vậy, thay flow definition trong registry thường sát với hành vi tích hợp hơn việc giả lập toàn bộ engine.

## 3. Xác định hợp đồng giữa flow cha và subflow

Trước khi viết stub, hãy ghi lại hợp đồng mà flow cha yêu cầu. Hợp đồng thường gồm:

1. **Subflow ID:** tên flow cha dùng để tra cứu flow con.
2. **Input:** tên, kiểu và ý nghĩa dữ liệu flow cha truyền vào.
3. **Output:** dữ liệu flow cha cần nhận lại, nếu có.
4. **End-state ID:** các kết quả mà flow cha xử lý như event.
5. **Vòng đời:** subflow bắt đầu và kết thúc trong phạm vi conversation nào.
6. **Điều kiện lỗi hoặc hủy:** kết quả nào cần quay lại, thử lại hoặc kết thúc hành trình.

Ví dụ, flow checkout gọi subflow chọn địa chỉ:

| Hợp đồng | Giá trị minh họa |
| --- | --- |
| Subflow ID | `address/select` |
| Input | `customerId` |
| Output | `selectedAddressId` |
| Kết quả thành công | `selected` |
| Kết quả hủy | `cancelled` |

Tên input và output phải thống nhất giữa flow cha, flow con và stub. Event kết thúc cũng là một phần của hợp đồng: nếu flow cha chờ `selected` nhưng stub kết thúc bằng `success`, transition mong đợi sẽ không được kích hoạt.

Hãy xem hợp đồng này như API giữa hai flow. Flow cha nên phụ thuộc vào các input, output và event công khai, không phụ thuộc vào state nội bộ, view hoặc service cụ thể bên trong subflow.

## 4. Ví dụ flow cha gọi subflow

Giả sử flow cha có state `selectAddress`, gọi subflow `address/select`, rồi chuyển tới `review` nếu địa chỉ được chọn hoặc quay về `shipping` nếu người dùng hủy.

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">

    <input name="customerId" type="java.lang.String"/>

    <view-state id="shipping" view="checkout/shipping">
        <transition on="chooseAddress" to="selectAddress"/>
    </view-state>

    <subflow-state id="selectAddress" subflow="address/select">
        <input>
            <input-attribute
                name="customerId"
                value="flowScope.customerId"/>
        </input>

        <transition on="selected" to="review"/>
        <transition on="cancelled" to="shipping"/>
    </subflow-state>

    <view-state id="review" view="checkout/review">
        <transition on="confirm" to="complete"/>
    </view-state>

    <end-state id="complete"/>
</flow>
~~~

Flow cha chỉ cần biết subflow có thể kết thúc với `selected` hoặc `cancelled`. Nó không cần biết subflow hiển thị bao nhiêu màn hình, gọi service nào hay sử dụng những state nội bộ nào.

Stub thành công có thể là một flow XML tối giản:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" type="java.lang.String"/>

    <end-state id="selected"/>
</flow>
~~~

Stub này nhận input `customerId` và kết thúc ngay với event `selected`. Nó đủ để kiểm tra flow cha chuyển tới `review` sau khi subflow hoàn tất.

Để kiểm tra nhánh hủy, dùng một fixture khác có cùng input nhưng kết thúc bằng `cancelled`:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" type="java.lang.String"/>

    <end-state id="cancelled"/>
</flow>
~~~

Hai fixture giữ cùng hợp đồng input và chỉ khác kết quả kết thúc. Có thể chọn fixture phù hợp bằng cấu hình registry của test. Không cần sửa flow cha chỉ để đổi kết quả giả lập.

## 5. Đăng ký subflow giả trong test registry

Flow cha tìm subflow bằng ID thông qua `FlowDefinitionRegistry` mà `FlowExecutor` sử dụng. Trong kiểm thử, tạo registry riêng cho test, đăng ký flow cha và đăng ký stub dưới đúng ID mà thuộc tính `subflow` tham chiếu.

Mô hình cấu hình:

~~~text
Test FlowDefinitionRegistry
    |
    +-- checkout/checkout  -> flow cha cần kiểm thử
    |
    +-- address/select     -> stub flow thành công
~~~

Khi chạy test nhánh hủy, thay fixture `address/select` bằng stub kết thúc `cancelled`:

~~~text
Test FlowDefinitionRegistry
    |
    +-- checkout/checkout  -> cùng flow cha
    |
    +-- address/select     -> stub flow hủy
~~~

Đây là sơ đồ cấu hình, không phải cú pháp đăng ký cụ thể của một phiên bản Spring Web Flow. Tùy cách dự án khởi tạo registry, có thể đăng ký fixture bằng XML resource, builder hoặc cấu hình Java. Điều cần giữ nguyên là:

- Flow cha được nạp từ định nghĩa cần kiểm thử.
- Stub được đăng ký bằng đúng ID subflow mà flow cha tham chiếu.
- `FlowExecutor` của test sử dụng registry này.
- Registry test tách khỏi registry production để không làm thay đổi cấu hình ứng dụng.

Không đăng ký hai flow definition cùng ID trong cùng registry rồi trông đợi engine tự chọn bản mong muốn. Mỗi test nên tạo cấu hình registry rõ ràng, chỉ có một định nghĩa cho ID subflow đang dùng.

## 6. Kiểm tra input được truyền sang subflow

Một stub tối giản chỉ kết thúc ngay có thể xác nhận flow cha khởi chạy được subflow, nhưng chưa chứng minh giá trị input được truyền đúng. Để kiểm tra input mapping, có thể dùng một test fixture có action hoặc probe bean ghi nhận giá trị nhận được.

Ví dụ, stub gọi một probe trong môi trường test:

~~~xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="customerId" type="java.lang.String"/>

    <action-state id="captureInput">
        <evaluate expression="subflowProbe.capture(customerId)"/>
        <transition on="success" to="selected"/>
    </action-state>

    <end-state id="selected"/>
</flow>
~~~

`subflowProbe` là bean chỉ được đăng ký trong test. Phương thức `capture` ghi lại `customerId` và trả về kết quả action phù hợp để flow tiếp tục. Cách cài đặt probe và kiểu kết quả action cần khớp phiên bản Web Flow đang dùng.

Trong test, đặt `customerId` của flow cha thành một giá trị dễ nhận biết, khởi chạy flow, gửi event để tới `selectAddress` và xác nhận probe đã nhận đúng giá trị. Không cần truy cập trực tiếp state hoặc biến nội bộ của flow con.

Một số điều cần kiểm tra:

- Input mapping dùng đúng tên thuộc tính.
- Biểu thức đọc đúng scope của flow cha.
- Giá trị có kiểu tương thích với input khai báo ở subflow.
- Giá trị không bị thay bằng dữ liệu mặc định hoặc dữ liệu của execution khác.

Nếu input là một đối tượng lớn, cân nhắc truyền ID hoặc một DTO nhỏ thay vì truyền toàn bộ entity. Subflow có thể truy vấn dữ liệu cần thiết qua service sau khi kiểm tra quyền.

## 7. Kiểm tra output và event kết thúc

Subflow có thể trả kết quả cho flow cha, ví dụ `selectedAddressId`. Khi đó, test cần xác nhận cả hai phần: event kết thúc được xử lý đúng và output được chuyển đúng nơi.

Hợp đồng output cần thống nhất:

- Tên output do flow con công bố.
- Biểu thức hoặc scope mà flow con dùng để tạo giá trị.
- Đích nhận output trong flow cha.
- State hoặc action tiếp theo sử dụng giá trị đó.

Có thể tạo stub thành công có một giá trị cố định trong flow scope rồi kết thúc bằng `selected`. Cấu hình output mapping của subflow-state trong flow cha phải tương ứng với cách flow con công bố output. Trong bài kiểm thử, xác nhận flow cha nhận được đúng ID cố định và state tiếp theo có thể sử dụng giá trị đó.

Không nên chỉ khẳng định flow đã tới `review` rồi kết luận output mapping đúng. Event kết thúc có thể điều hướng đúng ngay cả khi output bị thiếu hoặc ánh xạ sai. Hãy kiểm tra giá trị đầu ra độc lập.

Nếu subflow trả về nhiều kết quả, nên dùng tên end-state thể hiện ý nghĩa nghiệp vụ, ví dụ `selected`, `cancelled`, `notAvailable`. Tránh dùng một event chung như `done` cho nhiều kết quả khác nhau nếu flow cha cần xử lý các nhánh khác nhau.

## 8. Bộ ca kiểm thử cho flow cha

Với ví dụ chọn địa chỉ, có thể xây dựng ma trận sau:

| Tình huống | Stub subflow | Kết quả cần xác nhận ở flow cha |
| --- | --- | --- |
| Chọn địa chỉ thành công | Kết thúc `selected` | Flow cha chuyển tới `review` |
| Người dùng hủy | Kết thúc `cancelled` | Flow cha quay về `shipping` |
| Input mapping đúng | Probe ghi nhận `customerId` | Giá trị nhận đúng với flow cha |
| Output mapping đúng | Stub trả `selectedAddressId` cố định | Flow cha nhận đúng ID |
| Kết quả không được flow cha hỗ trợ | Stub kết thúc bằng event ngoài hợp đồng | Flow xử lý lỗi không khớp theo thiết kế |
| Hai execution độc lập | Cùng stub nhưng input khác nhau | Dữ liệu của hai execution không bị trộn |

Một test thành công không thay thế các test nhánh hủy. Tương tự, test event không khớp không nên bị bỏ qua chỉ vì production subflow hiện tại chưa phát event đó. Hợp đồng giữa hai flow có thể thay đổi trong tương lai; test giúp phát hiện khi một bên đổi tên kết quả mà bên còn lại chưa được cập nhật.

## 9. Ví dụ cấu trúc bài kiểm thử

Các tiện ích kiểm thử Spring Web Flow thường cho phép khởi chạy flow, gửi event qua external context giả lập và xác nhận state hiện tại. Tên lớp hoặc helper cụ thể có thể khác theo phiên bản và cách dự án cấu hình test. Dưới đây là mã giả thể hiện trình tự kiểm thử:

~~~java
@Test
void selectedAddressMovesParentToReview() {
    FlowExecutor executor = testExecutorWith(
        parentFlow("checkout/checkout"),
        stubSubflow("address/select", "selected")
    );

    TestFlowSession session = start(executor, "checkout/checkout");
    assertState(session, "shipping");

    sendEvent(session, "chooseAddress");

    assertState(session, "review");
}

@Test
void cancelledAddressSelectionReturnsToShipping() {
    FlowExecutor executor = testExecutorWith(
        parentFlow("checkout/checkout"),
        stubSubflow("address/select", "cancelled")
    );

    TestFlowSession session = start(executor, "checkout/checkout");
    sendEvent(session, "chooseAddress");

    assertState(session, "shipping");
}
~~~

`TestFlowSession`, `start`, `sendEvent`, `assertState` và các hàm tạo fixture trong ví dụ là tên minh họa cho helper của bộ test, không phải API chuẩn được bảo đảm của Spring Web Flow. Khi triển khai, có thể dùng test support của phiên bản dự án, chẳng hạn các lớp kiểm thử flow XML và external context giả lập, rồi ánh xạ các bước trên sang helper thực tế.

Một test nên tập trung vào một hành vi quan sát được. Nếu test thành công đồng thời kiểm tra input, output, hủy, session và lỗi service, khi thất bại sẽ khó xác định nguyên nhân. Hãy chia thành các test nhỏ theo hợp đồng.

## 10. Giữ ranh giới giữa test flow cha và test subflow

Stub flow giúp kiểm thử flow cha nhanh và ổn định, nhưng không chứng minh logic bên trong subflow thật hoạt động đúng. Cần có bộ test riêng cho subflow.

| Bộ test | Thành phần chạy thật | Thành phần thay thế |
| --- | --- | --- |
| Test flow cha | Flow cha, engine, transition và scope của cha | Subflow bằng stub |
| Test subflow | Flow con, state, action và validation của con | Service/gateway bên ngoài bằng mock hoặc fake |
| Test tích hợp | Flow cha và flow con thật | Chỉ thay hệ thống bên ngoài nếu cần |
| Test end-to-end | Cả ứng dụng qua HTTP và view thật | Thường không thay flow nội bộ |

Không nên đưa mọi trường hợp nghiệp vụ bên trong subflow vào test flow cha. Flow cha chỉ cần biết hợp đồng công khai. Các quy tắc như kiểm tra địa chỉ hợp lệ, lọc địa chỉ theo vùng hoặc lưu địa chỉ thuộc trách nhiệm của subflow và service liên quan.

Mặt khác, không nên chỉ có test cha với stub mà không có test tích hợp nào chạy subflow thật. Stub có thể vô tình giữ hợp đồng cũ trong khi flow con đã đổi input, output hoặc end-state. Một số test tích hợp giúp phát hiện sự lệch hợp đồng này.

## 11. Các lỗi thường gặp khi dùng subflow giả

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Flow cha không tìm thấy subflow | Stub không được đăng ký hoặc ID khác với thuộc tính `subflow` | Đăng ký đúng ID trong test registry |
| Flow cha dừng ở subflow-state | End-state ID của stub không khớp event mà transition chờ | Dùng đúng tên kết quả trong hợp đồng |
| Input của stub rỗng | Thiếu input mapping hoặc sai tên thuộc tính | Kiểm tra tên input, biểu thức và kiểu dữ liệu |
| Flow cha tới đúng state nhưng dữ liệu output sai | Output mapping không được kiểm tra hoặc sai tên | Xác nhận giá trị output riêng với state đích |
| Test chạy được khi đơn lẻ nhưng thất bại khi chạy cả suite | Registry hoặc fixture dùng chung bị thay đổi giữa test | Tạo registry độc lập hoặc khôi phục cấu hình sau mỗi test |
| Test cha thất bại do lỗi service của flow con | Đang chạy flow con thật trong bài test điều phối cha | Thay flow definition bằng stub; kiểm thử service ở bộ test phù hợp |
| Stub luôn trả thành công | Chỉ có một fixture cho mọi tình huống | Tạo fixture cho hủy, không khả dụng và các kết quả cần thiết |
| Test không phát hiện flow con đổi hợp đồng | Stub không được đồng bộ với input/output/end-state công khai | Bổ sung contract test hoặc test tích hợp chạy flow thật |

## 12. Quy trình tạo subflow giả có thể bảo trì

Khi kiểm thử một flow cha mới, hãy thực hiện theo trình tự:

1. **Đọc hợp đồng subflow.** Ghi lại ID, input, output và end-state mà flow cha sử dụng.
2. **Tạo test registry riêng.** Đăng ký flow cha cần kiểm thử và fixture subflow dưới đúng ID.
3. **Tạo stub tối thiểu.** Stub chỉ thực hiện phần cần để tạo kết quả xác định.
4. **Kiểm thử nhánh thành công.** Xác nhận flow cha nhận event và tới đúng state.
5. **Kiểm thử nhánh hủy hoặc kết quả thay thế.** Xác nhận transition tương ứng hoạt động.
6. **Kiểm tra input/output.** Dùng giá trị dễ nhận biết và probe test khi cần.
7. **Kiểm tra cô lập execution.** Chạy nhiều execution với dữ liệu khác nhau để phát hiện rò rỉ trạng thái.
8. **Giữ test subflow riêng.** Kiểm thử flow con thật và thêm một số test tích hợp để xác nhận hợp đồng giữa hai flow vẫn tương thích.

Stub không nên chứa logic nghiệp vụ thật. Nếu phải thêm nhiều state, nhiều điều kiện hoặc truy vấn dữ liệu vào stub, có thể đang kiểm thử quá nhiều trách nhiệm trong một fixture. Hãy giữ stub nhỏ và để test subflow đảm nhiệm các quy tắc nội bộ.

## 13. Tự kiểm tra

- Vì sao nên dùng stub subflow khi kiểm thử flow cha? Để cô lập điều phối của flow cha khỏi logic nội bộ của flow con.
- Stub cần đăng ký dưới ID nào? Đúng ID mà thuộc tính `subflow` của parent flow tham chiếu.
- End-state ID của subflow có ý nghĩa gì? Nó trở thành event mà flow cha dùng để chọn transition sau khi subflow kết thúc.
- Chỉ kiểm tra state đích có đủ chứng minh output mapping đúng không? Không. Phải kiểm tra giá trị output riêng.
- Mock service và stub flow có giống nhau không? Không. Mock service thay thế dependency của một flow; stub flow thay thế flow definition được gọi.
- Stub có chứng minh subflow thật hoạt động đúng không? Không. Cần test riêng cho flow con và một số test tích hợp.
- Vì sao registry test cần độc lập? Để thay thế flow definition trong phạm vi test mà không làm thay đổi cấu hình production hoặc ảnh hưởng test khác.
- Có nên đưa toàn bộ logic nghiệp vụ vào stub không? Không. Stub chỉ tạo kết quả xác định theo hợp đồng công khai.

Kiểm thử flow cha với subflow giả giúp xác nhận ranh giới tích hợp bằng những kết quả rõ ràng và lặp lại được. Khi kết hợp test cha với stub, test riêng cho subflow và một số test tích hợp chạy flow thật, ứng dụng Spring Web Flow có thể tái sử dụng hành trình mà vẫn giữ được khả năng kiểm thử và bảo trì.

