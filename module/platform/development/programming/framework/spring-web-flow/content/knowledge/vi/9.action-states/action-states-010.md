# Tổ chức nhiều hành động và kiểm soát thứ tự

Trong chương **Action-state**, một `action-state` là điểm trong flow dùng để chạy action và quyết định state tiếp theo dựa trên kết quả action. Khi một bước nghiệp vụ cần thực hiện nhiều công việc, Spring Web Flow cho phép khai báo nhiều action theo thứ tự. Engine xử lý chúng như một chuỗi: sau mỗi action, nó kiểm tra kết quả có khớp transition rời state hay không. Nếu khớp, flow chuyển state ngay và những action còn lại trong chuỗi không chạy. Nếu chưa khớp, action kế tiếp được thực thi.

Module `SPRING_WEB_FLOW` tập trung mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên; tích hợp Spring MVC; kiểm thử và phục hồi luồng khi có lỗi. Vì vậy, tổ chức action-state tốt giúp điều phối các bước kiểm tra, tính toán, lưu dữ liệu và xử lý kết quả một cách dễ đọc. Điều quan trọng là xác định rõ action nào phải chạy trước, kết quả nào được phép kết thúc chuỗi và lỗi nào phải chuyển sang nhánh xử lý riêng.

## 1. Action-state thực thi một chuỗi có thứ tự

Khi execution đi vào `action-state`, các action được cấu hình trong state được thực thi theo thứ tự khai báo. Sau mỗi action, Spring Web Flow lấy result event và tìm transition có thể áp dụng cho event đó.

- Nếu có transition phù hợp, transition được thực hiện và chuỗi action dừng tại đó.
- Nếu không có transition phù hợp với result hiện tại, engine tiếp tục action kế tiếp trong chuỗi.
- Nếu đã hết action mà không có transition phù hợp, flow không có đường ra hợp lệ cho kết quả đó và có thể phát sinh lỗi `NoMatchingTransitionException`.

Đây là cách hoạt động theo mẫu Chain of Responsibility. Action đầu tiên có cơ hội xử lý kết quả; nếu kết quả chưa yêu cầu rẽ nhánh, quyền xử lý tiếp tục được chuyển cho action sau. Vì thế, nhiều `<evaluate>` trong cùng một action-state không có nghĩa là tất cả luôn chạy. Một transition khớp sớm sẽ kết thúc chuỗi.

Ví dụ, một hồ sơ đăng ký cần được kiểm tra, tính phí và lưu bản nháp. Nếu kiểm tra thất bại, flow phải quay lại form ngay và không tính phí hoặc lưu. Nếu kiểm tra thành công, action tính phí chạy; nếu tính phí thành công, action lưu bản nháp chạy. Chỉ khi lưu thành công, flow mới chuyển sang màn hình xem lại.

## 2. Khai báo nhiều action trong một action-state

Ví dụ sau minh họa một chuỗi ba hành động. Mỗi action được đặt tên để kết quả có thể được phân biệt rõ trong transition:

```xml
<action-state id="prepareApplication">
    <evaluate expression="applicationActions.validate(application)">
        <attribute name="name" value="validate" />
    </evaluate>

    <evaluate expression="applicationActions.calculateFees(application)">
        <attribute name="name" value="calculateFees" />
    </evaluate>

    <evaluate expression="applicationActions.saveDraft(application)">
        <attribute name="name" value="saveDraft" />
    </evaluate>

    <transition on="validate.error" to="editApplication" />
    <transition on="calculateFees.error" to="feeError" />
    <transition on="saveDraft.error" to="saveError" />
    <transition on="saveDraft.success" to="reviewApplication" />
</action-state>
```

Thuộc tính `name` đặt tên cho action và trở thành phần định danh trong result event. Ví dụ, action `validate` trả event `error` sẽ tạo kết quả `validate.error`; action `saveDraft` trả `success` tạo kết quả `saveDraft.success`.

Trong chuỗi này:

1. `validate` chạy trước. Nếu trả `validate.error`, transition về `editApplication` khớp và hai action sau không chạy. Nếu trả `validate.success`, chưa có transition tương ứng nên chuỗi tiếp tục.
2. `calculateFees` chạy tiếp. Nếu trả `calculateFees.error`, flow chuyển sang `feeError`. Nếu trả `calculateFees.success`, chuỗi tiếp tục.
3. `saveDraft` chạy cuối. Kết quả `saveDraft.success` chuyển sang `reviewApplication`; `saveDraft.error` chuyển sang `saveError`.

Để mẫu này hoạt động như dự kiến, các phương thức được gọi cần trả kết quả event có tên tương ứng. Khi dùng POJO method, có thể trả `Event` với ID như `success` hoặc `error`; kiểu trả về và cách tạo event cần khớp API Spring Web Flow của phiên bản ứng dụng. Nếu action trả `Boolean`, Spring Web Flow ánh xạ `true` thành `yes` và `false` thành `no`; nếu trả `Enum`, tên enum được dùng làm event ID; các kiểu kết quả khác thường được ánh xạ thành `success`. Hãy đặt transition theo đúng quy tắc ánh xạ đó.

## 3. Đặt tên action và thiết kế result event

Tên action giúp phân biệt kết quả khi có nhiều action trong cùng một state. Nếu không đặt tên, việc đọc log, định nghĩa transition và kiểm thử chuỗi dài có thể khó hơn vì nhiều action cùng trả các event phổ biến như `success` hoặc `error`.

Một action nên trả kết quả có ý nghĩa đối với flow, ví dụ:

| Action | Result event | Ý nghĩa |
|---|---|---|
| `validate` | `validate.success` | Dữ liệu hợp lệ, có thể tiếp tục |
| `validate` | `validate.error` | Dữ liệu không hợp lệ, quay lại form |
| `calculateFees` | `calculateFees.success` | Tính phí hoàn tất |
| `calculateFees` | `calculateFees.error` | Không thể tính phí theo dữ liệu hiện tại |
| `saveDraft` | `saveDraft.success` | Bản nháp đã được lưu |
| `saveDraft` | `saveDraft.error` | Lưu bản nháp thất bại |

Không nên tạo quá nhiều event chỉ để phản ánh chi tiết kỹ thuật. Event nên thể hiện quyết định mà flow cần đưa ra. Nếu flow cần phân biệt lỗi dữ liệu, lỗi nghiệp vụ và lỗi hạ tầng, có thể dùng event riêng hoặc lưu mã lỗi an toàn vào context để nhánh xử lý phù hợp đọc được.

Khi một action trả event không có transition khớp, engine tiếp tục action kế tiếp. Điều này hữu ích cho các kết quả `success` trung gian, nhưng cũng có thể che giấu lỗi nếu bạn quên khai báo transition cho event cần dừng. Hãy liệt kê các result event có thể trả về và quyết định rõ event nào tiếp tục, event nào rẽ nhánh, event nào là lỗi không thể xử lý tại state hiện tại.

## 4. Lưu kết quả trung gian vào flow scope

Action thường cần tạo dữ liệu cho action sau hoặc state tiếp theo. Có thể dùng thuộc tính `result` của `<evaluate>` để lưu giá trị trả về vào flow scope hoặc scope phù hợp.

```xml
<action-state id="loadAndAssessApplication">
    <evaluate expression="applicationService.loadRules(application.type)"
              result="flowScope.rules" />

    <evaluate expression="applicationService.assess(application, rules)"
              result="flowScope.assessment">
        <attribute name="name" value="assess" />
    </evaluate>

    <transition on="assess.accepted" to="calculateFees" />
    <transition on="assess.rejected" to="showRejection" />
</action-state>
```

Ở đây, kết quả `loadRules` được lưu vào `flowScope.rules`, để action `assess` sử dụng. Kết quả đánh giá được lưu vào `flowScope.assessment` và đồng thời được dùng làm result event của action để chọn transition. Chọn scope theo vòng đời cần thiết: `viewScope` cho dữ liệu riêng view, `flowScope` cho dữ liệu cần qua nhiều state, và `conversationScope` khi flow cha cùng subflow cần chia sẻ dữ liệu theo thiết kế.

Không lưu mọi giá trị trung gian vào `flowScope` theo thói quen. Chỉ giữ dữ liệu mà state sau cần. Dữ liệu nhạy cảm, entity lớn hoặc đối tượng phụ thuộc request không nên được giữ lâu trong flow. Dữ liệu do form gửi lên vẫn phải được xác thực và kiểm tra quyền ở service layer trước khi dùng để thay đổi nghiệp vụ.

## 5. Tổ chức chuỗi action thành nhiều state

Đặt nhiều action trong một action-state phù hợp khi chúng là một bước xử lý liên tục, không cần giao diện xen giữa và có cùng ranh giới điều phối. Tuy nhiên, nếu từng bước có ý nghĩa nghiệp vụ độc lập, cần theo dõi riêng, có khả năng retry hoặc cần nhánh phục hồi riêng, hãy tách thành nhiều action-state.

Ví dụ:

```xml
<action-state id="validateApplication">
    <evaluate expression="applicationActions.validate(application)" />
    <transition on="success" to="calculateApplicationFees" />
    <transition on="error" to="editApplication" />
</action-state>

<action-state id="calculateApplicationFees">
    <evaluate expression="applicationActions.calculateFees(application)" />
    <transition on="success" to="saveApplicationDraft" />
    <transition on="error" to="feeError" />
</action-state>

<action-state id="saveApplicationDraft">
    <evaluate expression="applicationActions.saveDraft(application)" />
    <transition on="success" to="reviewApplication" />
    <transition on="error" to="saveError" />
</action-state>
```

Flow chuyển state theo thứ tự validate → calculate → save. Cách này làm cho từng bước hiện rõ trong flow definition và cho phép định nghĩa đường lỗi cụ thể. Nó cũng tạo thêm state và transition, nên không cần tách vụn những thao tác rất nhỏ không có ý nghĩa độc lập.

| Tiêu chí | Một action-state có nhiều action | Nhiều action-state nối tiếp |
|---|---|---|
| Bản chất công việc | Một bước xử lý có chuỗi action nội bộ | Nhiều bước nghiệp vụ có ranh giới riêng |
| Điều phối | Kết quả action có thể kết thúc chuỗi sớm | Transition quyết định bước tiếp theo sau mỗi state |
| Khả năng quan sát | Thấy kết quả ở cấp chuỗi hoặc nhánh | Có thể theo dõi state đang xử lý |
| Xử lý lỗi | Các lỗi phải được ánh xạ thành event và transition phù hợp | Mỗi state có thể có nhánh lỗi và điểm phục hồi riêng |
| Độ phức tạp định nghĩa | Ít state hơn, chuỗi action có thể dài | Nhiều state hơn, đường đi tường minh hơn |

Action-state chạy trong quá trình xử lý flow request; nó không tự tạo một hàng đợi hoặc cơ chế chạy nền. Nếu một bước mất nhiều phút, cần chờ người khác phê duyệt hoặc phải tiếp tục sau khi phiên web kết thúc, hãy xem xét lưu trạng thái nghiệp vụ bền vững và dùng cơ chế xử lý nền/workflow phù hợp.

## 6. Phân biệt action-state với transition action và decision-state

Không phải mọi nhóm action đều cần được đặt trong một action-state. Chọn vị trí theo thời điểm và mục đích của hành động.

| Vị trí | Khi nào dùng | Đặc điểm |
|---|---|---|
| `action-state` | Cần chạy action sau khi đi vào một state xử lý, rồi điều hướng theo kết quả | Có thể khai báo chuỗi action theo thứ tự và dừng khi result khớp transition |
| Action trong `transition` | Hành động chỉ thuộc một event cụ thể của state hiện tại | Chỉ chạy khi transition đó được chọn |
| `on-entry` | Chuẩn bị dữ liệu hoặc tài nguyên khi đi vào state | Có thể khai báo nhiều action, chạy theo thứ tự khai báo |
| `on-exit` | Dọn dẹp hoặc ghi nhận khi rời một state | Áp dụng cho các đường ra của state đó |
| `decision-state` | Chỉ cần chọn đường đi theo điều kiện | Dùng biểu thức if/else, không phải nơi thực hiện chuỗi side effect |

Ví dụ, sau khi người dùng submit form, action ghi câu trả lời có thể nằm trong transition `submit`; action-state kế tiếp kiểm tra có cần bước bổ sung hay không. Nếu chỉ cần rẽ nhánh theo một điều kiện boolean, `decision-state` thường diễn đạt trực tiếp hơn:

```xml
<decision-state id="checkEligibility">
    <if test="eligibilityService.isEligible(application)"
        then="collectAdditionalDetails"
        else="showIneligible" />
</decision-state>
```

Nếu điều kiện kiểm tra có tác dụng phụ, cần gọi hệ thống ngoài hoặc cần xử lý lỗi như một action, hãy dùng action-state hoặc service thích hợp. Decision-state nên tập trung vào quyết định định tuyến.

## 7. Giữ thứ tự action an toàn và dễ bảo trì

Thứ tự khai báo là một phần của logic nghiệp vụ. Trước khi sắp xếp action, xác định phụ thuộc dữ liệu và tác dụng phụ của từng bước.

Một chuỗi thường gặp:

1. Kiểm tra dữ liệu đầu vào và quyền truy cập.
2. Đọc dữ liệu tham chiếu đáng tin cậy từ hệ thống.
3. Tính toán hoặc đánh giá điều kiện nghiệp vụ.
4. Ghi thay đổi vào kho dữ liệu trong ranh giới transaction phù hợp.
5. Trả kết quả hoặc chuyển sang state tiếp theo.

Các nguyên tắc quan trọng:

- Không thực hiện ghi dữ liệu trước khi hoàn tất những kiểm tra bắt buộc.
- Không dựa vào giá trị nhạy cảm do client gửi để quyết định quyền, giá hoặc chủ sở hữu tài nguyên.
- Đưa transaction vào service/domain layer; action-state chỉ điều phối lời gọi.
- Với thao tác có thể được gửi lại, dùng idempotency key, ràng buộc duy nhất hoặc cơ chế chống xử lý trùng.
- Giữ action ngắn và có một trách nhiệm rõ; tách method Java để có thể unit test.
- Không gọi nhiều hệ thống ngoài đồng bộ trong một chuỗi request dài nếu có thể chuyển công việc sang xử lý nền.
- Đặt tên action, event và state theo ngôn ngữ nghiệp vụ để người đọc hiểu được vì sao thứ tự đó tồn tại.

Action-state không chạy các action song song. Các action trong chuỗi được thực thi tuần tự theo thứ tự khai báo và kết quả của action trước có thể quyết định liệu action sau có được chạy hay không. Nếu nghiệp vụ thật sự cần xử lý song song, hãy điều phối bằng service hoặc cơ chế xử lý bất đồng bộ phù hợp, sau đó đưa kết quả tổng hợp trở lại flow.

## 8. Xử lý lỗi và phục hồi chuỗi action

Mỗi action cần có hợp đồng kết quả rõ ràng. Một action có thể trả thành công, trả event nghiệp vụ khác hoặc ném exception. Đây là ba tình huống khác nhau:

- **Kết quả thành công:** chuỗi tiếp tục nếu không có transition khớp; hoặc chuyển state nếu đã khai báo transition cho event đó.
- **Kết quả lỗi có chủ đích:** action trả event như `error`, `invalid` hoặc `unavailable`; flow có thể chuyển sang state hiển thị lỗi, cho sửa dữ liệu hoặc cho thử lại.
- **Exception:** lỗi thực thi như timeout, lỗi database hoặc bug. Cần được xử lý theo cơ chế exception phù hợp của flow/ứng dụng; không giả định nó tự trở thành event `error`.

Ví dụ, nếu `calculateFees` không thể truy cập dịch vụ giá, có thể trả event `unavailable` để chuyển tới state thông báo hoặc cho người dùng thử lại. Nếu action ném exception ngoài dự kiến, cần ghi log có mã tương quan, bảo vệ dữ liệu nhạy cảm và định nghĩa chính sách lỗi ở tầng ứng dụng.

Không nên bắt mọi exception rồi trả `success`. Điều đó khiến chuỗi tiếp tục với dữ liệu chưa được tạo hoặc chưa được lưu, dẫn tới trạng thái flow và dữ liệu nghiệp vụ không nhất quán. Ngược lại, lỗi không quan trọng như metric phụ có thể được xử lý riêng nếu nghiệp vụ cho phép tiếp tục.

Nếu cần retry, hãy phân biệt lỗi tạm thời với lỗi không thể phục hồi. Giới hạn số lần thử, đặt timeout, bảo đảm action có thể chạy lặp an toàn hoặc có cơ chế đối soát. Không tự động retry một thao tác thanh toán hoặc tạo đơn không idempotent chỉ vì request trước bị timeout; hệ thống có thể đã hoàn tất thao tác dù client chưa nhận phản hồi.

## 9. Kiểm thử thứ tự và nhánh của nhiều action

Kiểm thử action-state cần xác minh thứ tự gọi, điều kiện dừng chuỗi, dữ liệu truyền giữa các action và state cuối cùng. Chỉ kiểm tra từng service method riêng lẻ sẽ không phát hiện được lỗi cấu hình transition khiến action chạy sai thứ tự.

Với chuỗi `validate` → `calculateFees` → `saveDraft`, nên bao phủ:

| Kịch bản | Điều cần xác minh |
|---|---|
| Cả ba action thành công | Thứ tự gọi là validate, calculateFees, saveDraft; flow tới review |
| Validation trả lỗi | Flow quay lại form; calculateFees và saveDraft không chạy |
| Tính phí trả lỗi | Validation đã chạy; saveDraft không chạy; flow tới feeError |
| Lưu bản nháp trả lỗi | Hai bước trước đã chạy; flow tới saveError |
| Action trả event không có transition | Chuỗi tiếp tục theo quy tắc; nếu hết action không có đường ra phù hợp, lỗi được phát hiện |
| Action ném exception | Exception được xử lý theo chính sách; không bị biến thành thành công giả |
| Request được gửi lại | Side effect không tạo dữ liệu trùng ngoài ý muốn |
| Flow scope chứa dữ liệu trung gian | Giá trị cần cho action/state sau được lưu và đọc đúng |

Spring Web Flow cung cấp test support để khởi chạy flow, gửi event và kiểm tra state hiện tại. API cụ thể phụ thuộc phiên bản. Có thể dùng mock/spy cho bean action để xác minh thứ tự và số lần gọi, kết hợp kiểm thử tích hợp cho flow definition.

Ví dụ các khẳng định cần có trong test (mã giả):

```java
// Khi validation thất bại, các action phía sau không được gọi.
assertThat(flow.currentState()).isEqualTo("editApplication");
verify(applicationActions).validate(any());
verify(applicationActions, never()).calculateFees(any());
verify(applicationActions, never()).saveDraft(any());

// Khi cả chuỗi thành công, thứ tự phải được giữ.
InOrder order = inOrder(applicationActions);
order.verify(applicationActions).validate(any());
order.verify(applicationActions).calculateFees(any());
order.verify(applicationActions).saveDraft(any());
assertThat(flow.currentState()).isEqualTo("reviewApplication");
```

Đây là minh họa về điều cần xác minh; cách tạo execution, gửi event và lấy state cần dùng API test support tương ứng với phiên bản dự án. Hãy kiểm thử cả service layer để bảo đảm quy tắc nghiệp vụ và transaction đúng ngay cả khi service được gọi từ nơi khác ngoài flow.

## 10. Checklist khi thiết kế một action-state có nhiều hành động

Trước khi hoàn thiện chuỗi action, hãy trả lời:

1. Mỗi action làm một việc gì và phụ thuộc dữ liệu nào từ action trước?
2. Thứ tự khai báo đã phản ánh đúng thứ tự nghiệp vụ chưa?
3. Result event của từng action là gì? Có transition cho tất cả kết quả cần kết thúc chuỗi không?
4. Event nào được phép tiếp tục sang action kế tiếp? Có nguy cơ một kết quả lỗi không khớp transition rồi vô tình chạy tiếp không?
5. Action nào có side effect? Transaction và idempotency được bảo đảm ở đâu?
6. Có nên gom các action vào một state hay tách thành nhiều state để quan sát và phục hồi riêng?
7. Dữ liệu trung gian được lưu ở scope nào và có cần thiết sau khi flow chuyển state không?
8. Có kiểm thử thứ tự, nhánh lỗi, exception, request lặp và dữ liệu scope không?

Nếu một chuỗi có nhiều nhánh hoặc tác dụng phụ khó hiểu, hãy tách action thành các method có tên rõ ràng và cân nhắc chia state theo ranh giới nghiệp vụ. Flow definition nên giúp người đọc thấy được trình tự và quyết định, không trở thành nơi chứa toàn bộ thuật toán.

## Kết luận

`action-state` tổ chức các action thành một chuỗi tuần tự. Sau mỗi action, Spring Web Flow kiểm tra result event; nếu có transition khớp, flow chuyển state và dừng chuỗi, nếu không thì action kế tiếp được thực thi. Cơ chế này giúp kết hợp các bước kiểm tra, tính toán và lưu dữ liệu cùng các nhánh xử lý lỗi.

Để kiểm soát thứ tự an toàn, hãy đặt tên action và event rõ ràng, khai báo transition cho kết quả quan trọng, lưu dữ liệu trung gian đúng scope và giữ transaction trong service/domain layer. Dùng một action-state cho chuỗi nội bộ gắn kết; tách thành nhiều state khi cần quan sát, phục hồi hoặc kiểm thử từng bước độc lập. Kiểm thử cả thứ tự gọi lẫn hành vi dừng chuỗi sẽ giúp flow phản ánh đúng trình tự nghiệp vụ.
