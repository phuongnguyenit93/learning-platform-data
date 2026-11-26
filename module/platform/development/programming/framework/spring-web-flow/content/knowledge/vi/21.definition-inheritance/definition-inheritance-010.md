# Kiểm thử định nghĩa sau hợp nhất để phát hiện cấu hình ngoài ý muốn

Trong module **SPRING_WEB_FLOW**, kế thừa flow giúp nhiều hành trình dùng chung input, dữ liệu khởi tạo, state và transition. Flow con có thể bổ sung hoặc ghi đè một phần định nghĩa của flow cha. Kết quả chạy thực tế được tạo từ định nghĩa sau khi framework xử lý quan hệ kế thừa, vì vậy chỉ đọc XML của flow con chưa đủ để biết toàn bộ cấu hình cuối cùng.

Một thay đổi nhỏ ở flow cha có thể ảnh hưởng nhiều flow con. Một state con trùng ID với state cha có thể thay đổi view hoặc kết hợp các transition theo quy tắc merge của Spring Web Flow. Nếu không kiểm thử kết quả sau hợp nhất, ứng dụng có thể vô tình mất transition hủy, chạy action khởi tạo hai lần, thay đổi model binding hoặc điều hướng tới state không còn phù hợp. Bài này hướng dẫn cách kiểm tra định nghĩa đã hợp nhất và kiểm thử hành vi của flow con để phát hiện các sai lệch đó.

## 1. Vì sao phải kiểm thử sau hợp nhất?

Khi một flow kế thừa flow khác, định nghĩa cuối cùng được xây dựng từ nhiều nguồn:

- Flow cha cung cấp cấu hình dùng chung như input, biến, action vòng đời, state và transition.
- Flow con có thể thêm state hoặc tùy chỉnh state kế thừa theo quy tắc kế thừa của framework.
- Flow con có thể thêm cấu hình riêng như view, action, transition hoặc xử lý lỗi.
- Cấu hình builder, registry và các bean được tham chiếu cũng ảnh hưởng tới khả năng xây dựng và thực thi flow.

Do đó, cần kiểm tra hai lớp kết quả:

1. **Cấu trúc sau hợp nhất:** flow con có những state, input, transition, action và thuộc tính nào sau khi được registry xây dựng?
2. **Hành vi khi thực thi:** khi gửi event vào flow con, state nào được kích hoạt, action nào chạy, dữ liệu nào được bind và flow kết thúc hoặc phục hồi ra sao?

Kiểm tra cấu trúc giúp phát hiện cấu hình thiếu hoặc thừa trước khi chạy. Kiểm thử hành vi xác nhận cấu hình đó thực sự tạo ra hành trình mong muốn.

## 2. Ví dụ flow cha và flow con

Giả sử ứng dụng có quy trình chỉnh sửa booking chung. Flow cha giữ input `bookingId`, tải booking và cung cấp state chỉnh sửa cùng transition hủy:

```xml
<flow id="baseBooking" abstract="true">
    <input name="bookingId" type="long" />

    <on-start>
        <evaluate expression="bookingFlowService.loadEditable(bookingId)"
                  result="flowScope.booking" />
    </on-start>

    <view-state id="editBooking" view="booking/edit" model="booking">
        <transition on="cancel" to="cancelled" />
    </view-state>

    <end-state id="cancelled" />
</flow>
```

Flow dành cho khách hàng VIP kế thừa cấu hình chung, thay view chỉnh sửa và bổ sung nhánh gửi để xem lại:

```xml
<flow id="vipBooking" parent="baseBooking">
    <view-state id="editBooking" view="booking/vip-edit" model="booking">
        <transition on="submit" to="reviewBooking" />
    </view-state>

    <view-state id="reviewBooking" view="booking/review" />
</flow>
```

Trong ví dụ, `editBooking` của flow con có cùng ID với state trong flow cha. Ý đồ cấu hình là dùng view VIP, giữ model booking, giữ khả năng hủy được kế thừa và thêm event `submit` dẫn tới `reviewBooking`. Các chi tiết merge cụ thể cần được xác nhận trên phiên bản Spring Web Flow và cấu hình builder mà ứng dụng đang sử dụng; không suy luận rằng XML con luôn thay thế toàn bộ state cha hoặc luôn giữ mọi phần tử cha.

Một bộ kiểm thử cho `vipBooking` cần xác nhận kết quả sau hợp nhất đúng với ý đồ:

| Thành phần | Kết quả mong đợi |
|---|---|
| Flow ID | `vipBooking` là flow có thể khởi chạy |
| Input | `bookingId` vẫn được khai báo và truyền vào được |
| `on-start` | `loadEditable` chạy đúng số lần và đặt `booking` vào `flowScope` |
| State `editBooking` | View được chọn là `booking/vip-edit`, model vẫn là `booking` |
| Transition `cancel` | Nhánh hủy kế thừa vẫn dẫn tới `cancelled` |
| Transition `submit` | Nhánh mới dẫn tới `reviewBooking` |
| State `reviewBooking` | View review của flow con được kích hoạt |

Nếu một trong các kết quả trên không đúng, cần xem lại định nghĩa cha/con và quy tắc merge thay vì sửa assertion để chấp nhận hành vi ngoài ý muốn.

## 3. Xác nhận registry xây dựng được flow con

Trước khi kiểm thử từng event, hãy để ứng dụng hoặc test context khởi tạo flow registry bằng đúng tài nguyên và `FlowBuilderServices` mà môi trường chạy thật sử dụng. Registry cần tìm được cả flow cha lẫn flow con, và phải giải quyết được quan hệ `parent`.

Các kiểm tra cấu trúc ban đầu nên xác nhận:

- Tài nguyên flow cha được đăng ký với ID đúng và có thể được dùng làm parent.
- Flow con tham chiếu đúng ID cha; không trỏ nhầm một flow khác có tên gần giống.
- Flow con được đăng ký với ID riêng và có thể được khởi chạy theo ID đó.
- Không có state ID trùng ngoài chủ đích, transition trỏ tới state không tồn tại hoặc biểu thức tham chiếu bean không được đăng ký.
- Các input, biến và kiểu dữ liệu được khai báo tương thích với action cùng view sử dụng chúng.
- Flow có thể được xây dựng với cùng expression parser, conversion service và validator như môi trường ứng dụng.

Việc registry khởi tạo thành công là một kiểm tra quan trọng, nhưng chưa chứng minh hành vi sau hợp nhất đúng. Một flow có thể parse thành công dù transition hợp lệ về mặt cấu trúc nhưng dẫn người dùng tới nhánh nghiệp vụ sai.

## 4. Kiểm tra state và transition được kế thừa hoặc ghi đè

State thường là nơi có nhiều thay đổi khi kế thừa. Một flow con có thể dùng lại state của cha, thêm state mới hoặc khai báo state cùng ID để tùy chỉnh. Với từng state quan trọng, lập bảng hợp đồng gồm các thuộc tính phải giữ, các thuộc tính được phép thay đổi và các event phải được hỗ trợ.

Ví dụ hợp đồng của `editBooking`:

| Thuộc tính | Từ flow cha | Ý đồ của flow con | Cần kiểm tra |
|---|---|---|---|
| ID state | `editBooking` | Giữ nguyên ID | State tồn tại đúng một lần trong flow con |
| View | `booking/edit` | Đổi thành `booking/vip-edit` | View VIP được chọn |
| Model | `booking` | Giữ nguyên | Model attribute trỏ tới đúng đối tượng |
| Event `cancel` | Dẫn tới `cancelled` | Giữ lại | Event vẫn hoạt động |
| Event `submit` | Chưa có | Bổ sung | Event dẫn tới `reviewBooking` |

Không chỉ kiểm tra transition mới. Một lỗi merge thường xuất hiện ở phần cấu hình cũ bị mất hoặc bị thay đổi ngoài ý muốn. Vì vậy, mỗi lần override state nên có assertion cho cả hành vi mới và hành vi kế thừa cần giữ.

Ngoài ra, kiểm tra những state không bị override. Nếu flow con chỉ tùy chỉnh `editBooking`, các state chung khác như `cancelled`, `error` hoặc `completed` vẫn cần hiện diện theo thiết kế. Việc kiểm tra danh sách state mong đợi giúp phát hiện state bị loại khỏi kết quả hợp nhất.

## 5. Kiểm tra input, biến và dữ liệu khởi tạo

Input và biến được kế thừa có thể là hợp đồng giữa nhiều state. Nếu flow con vô tình đổi tên hoặc đổi kiểu, các biểu thức trong `on-start`, action và view có thể đọc sai dữ liệu.

Với ví dụ booking, hãy kiểm tra:

- `bookingId` có được nhận khi khởi chạy `vipBooking` không.
- Giá trị `bookingId` có đúng kiểu và được chuyển đổi theo cấu hình không.
- `loadEditable` nhận đúng ID và chỉ chạy theo số lần dự kiến.
- Kết quả được lưu vào `flowScope.booking`, không bị ghi nhầm sang một scope hoặc tên biến khác.
- State `editBooking` đọc đúng model đã khởi tạo.
- Nếu flow con khai báo thêm input cùng tên, kiểu hoặc giá trị mặc định có còn tương thích với caller không.

Đặc biệt, kiểm thử số lần gọi action khởi tạo. Khi flow cha và flow con cùng có action vòng đời hoặc action cùng được cấu hình ở nhiều nơi, thay đổi merge có thể làm một thao tác bị gọi nhiều lần. Với thao tác đọc dữ liệu, gọi hai lần có thể làm tăng chi phí; với thao tác giữ chỗ hoặc tạo bản ghi, gọi lặp có thể gây sai nghiệp vụ.

## 6. Kiểm tra binder và validation sau hợp nhất

Một flow cha có thể định nghĩa `model`, `<binder>` và validation cho form. Khi flow con thay view hoặc bổ sung field, cấu hình binding cần được kiểm tra lại. Việc view con hiển thị thêm một input không tự động có nghĩa property đó được phép bind.

Ví dụ, nếu flow cha chỉ cho phép sửa tên và email:

```xml
<view-state id="editBooking" view="booking/edit" model="booking">
    <binder>
        <binding property="customer.name" />
        <binding property="customer.email" />
    </binder>
    <transition on="submit" to="reviewBooking" bind="true" validate="true" />
</view-state>
```

Flow con đổi view sang `booking/vip-edit` và thêm trường ghi chú VIP. Cần quyết định rõ `note` có được phép bind hay không. Nếu có, hãy khai báo và kiểm thử property path đó trong cấu hình con theo đúng quy tắc merge. Nếu không, việc view hiển thị field không được phép bind phải được phát hiện bằng kiểm thử request.

Các ca kiểm thử cần có:

- Field được kế thừa vẫn bind vào đúng property.
- Field mới của flow con chỉ bind khi đã được cho phép.
- Property nhạy cảm như `ownerId`, `totalPrice`, `approved` không thể bị cập nhật bằng request giả mạo.
- Validation của cha vẫn chạy hoặc được thay thế đúng như ý đồ.
- Lỗi chuyển đổi kiểu và lỗi validation giữ flow ở view-state phù hợp.
- Message lỗi gắn đúng property path trong view con.

## 7. Kiểm tra action, thứ tự thực thi và exception handler

Action có thể xuất hiện ở `on-start`, `on-entry`, `on-render`, `on-exit`, transition hoặc `action-state`. Sau hợp nhất, cần xác nhận action nào được gọi, theo thứ tự nào và trong những nhánh nào.

Với từng action quan trọng, ghi rõ:

| Điểm thực thi | Câu hỏi cần kiểm thử |
|---|---|
| `on-start` | Action khởi tạo có chạy đúng một lần khi child flow bắt đầu không? |
| `on-entry` | Khi vào state được kế thừa hoặc override, action chuẩn bị view nào được gọi? |
| `on-render` | Refresh hoặc validation lỗi có làm action chạy lại không? |
| Transition action | Chỉ event tương ứng mới kích hoạt action phải không? |
| `on-exit` | Khi rời state qua cả nhánh submit và cancel, cleanup có chạy đúng không? |
| `action-state` | Event trả về có khớp transition của flow con không? |

Nếu flow cha có exception handler hoặc action phục hồi, kiểm tra flow con vẫn xử lý đúng loại lỗi và không vô tình bỏ qua handler cần thiết. Kiểm tra cả lỗi nghiệp vụ có thể phục hồi lẫn lỗi kỹ thuật ngoài dự kiến. Không chỉ xác nhận có trang lỗi; cần xác nhận flow không tiếp tục sang state thành công khi action thất bại.

## 8. Kiểm thử hành vi của flow con

Kiểm thử hành vi nên khởi chạy **flow con** qua flow registry/executor, để Spring Web Flow thực sự xây dựng định nghĩa đã hợp nhất. Kiểm thử riêng flow cha không chứng minh flow con hoạt động đúng sau khi override.

Với test support của Spring Web Flow, có thể dùng `MockExternalContext` để gửi event và kiểm tra state hiện tại. Cách tổ chức sau là pseudocode mô tả các bước của test harness; tên helper cụ thể phụ thuộc base test class và phiên bản thư viện trong dự án:

```java
@Test
void vipFlowKeepsInheritedCancelAndAddsSubmit() {
    MockExternalContext context = new MockExternalContext();
    context.putRequestParameter("bookingId", "42");

    flowTestHarness.start("vipBooking", context);
    assertCurrentState("editBooking", context);
    assertRenderedView("booking/vip-edit", context);
    verify(bookingFlowService).loadEditable(42L);

    context.setEventId("submit");
    flowTestHarness.resume(context);
    assertCurrentState("reviewBooking", context);

    // Khởi chạy một execution mới để kiểm tra transition được kế thừa.
    MockExternalContext cancelContext = new MockExternalContext();
    cancelContext.putRequestParameter("bookingId", "42");
    flowTestHarness.start("vipBooking", cancelContext);
    cancelContext.setEventId("cancel");
    flowTestHarness.resume(cancelContext);
    assertCurrentState("cancelled", cancelContext);
}
```

Đoạn trên minh họa cách kiểm tra hai nhánh độc lập. Trong test thực tế, cấu hình mock service và assertion theo API của test support đang dùng; không coi `flowTestHarness` là một lớp có sẵn của framework. Dùng execution mới cho nhánh `cancel` giúp test không bị ảnh hưởng bởi việc execution đầu tiên đã chuyển sang `reviewBooking`.

Một bộ test cho flow con nên bao phủ tối thiểu:

1. Khởi chạy child flow với input hợp lệ và xác nhận state đầu tiên.
2. Kiểm tra dữ liệu được khởi tạo và action cha được gọi đúng số lần.
3. Gửi event kế thừa như `cancel` và xác nhận state đích.
4. Gửi event mới của child như `submit` và xác nhận state đích.
5. Gửi event không được khai báo và xác nhận lỗi/điều kiện không hợp lệ được xử lý theo cấu hình.
6. Gửi form với field hợp lệ, field sai kiểu và field ngoài allowlist.
7. Giả lập lỗi service và xác nhận exception handler hoặc nhánh lỗi đúng.
8. Kiểm tra kết thúc flow và dữ liệu trả về cho caller nếu child là subflow.

## 9. Kiểm tra kế thừa nhiều tầng và thay đổi ở flow cha

Một flow có thể kế thừa từ flow trung gian, ví dụ `baseBooking` → `standardBooking` → `vipBooking`. Khi đó, thay đổi ở `baseBooking` có thể ảnh hưởng cả hai tầng con; thay đổi ở `standardBooking` có thể ảnh hưởng riêng `vipBooking`.

Với chuỗi kế thừa, cần kiểm thử:

- Parent trực tiếp mà child khai báo có đúng như thiết kế không.
- State hoặc action được thêm ở tầng trung gian có xuất hiện trong flow cuối không.
- Override ở tầng cuối có thay đổi đúng thuộc tính dự kiến không.
- Cấu hình từ tầng gốc vẫn tồn tại khi không bị ghi đè.
- Không có action hoặc transition bị nhân đôi qua nhiều tầng.
- Không có state ID hoặc tên biến bị trùng ngoài ý muốn.

Khi thay đổi flow cha, chạy lại bộ test của tất cả flow con phụ thuộc. Nếu có nhiều flow con, tạo một bảng quan hệ parent-child trong tài liệu thiết kế hoặc test suite để CI biết những flow nào cần kiểm tra lại. Không chỉ chạy test của flow cha rồi kết luận các flow con vẫn an toàn.

## 10. Phân biệt lỗi xây dựng định nghĩa và lỗi hành vi

Hai nhóm lỗi cần cách xử lý khác nhau:

| Nhóm lỗi | Ví dụ | Cách phát hiện |
|---|---|---|
| Lỗi xây dựng/parse | Không tìm thấy parent, state ID trùng, transition trỏ tới state không tồn tại, biểu thức sai cú pháp | Khởi tạo registry và build flow trong test context |
| Lỗi hợp nhất cấu hình | View bị thay ngoài ý muốn, transition kế thừa bị mất, binder hoặc action bị thay đổi | Kiểm tra cấu trúc flow con sau khi registry xây dựng |
| Lỗi điều phối khi chạy | Event dẫn sai state, action chạy hai lần, nhánh lỗi đi tới success | Flow execution test với event và mock service |
| Lỗi dữ liệu | Input sai kiểu, model thiếu property, field không được phép vẫn bind | Binding/validation test với request hợp lệ và request giả mạo |
| Lỗi phục hồi | Execution lỗi nhưng không có đường quay lại, cleanup không chạy | Test exception, retry, refresh và kết thúc flow |

Nếu registry không thể xây dựng flow, hãy xử lý cấu hình và tài nguyên trước. Nếu registry thành công nhưng state hoặc event sai, xem lại kết quả hợp nhất và kiểm thử hành vi. Phân loại đúng giúp tìm nguyên nhân nhanh hơn và tránh thêm cấu hình chữa cháy ở flow con.

## 11. Nguyên tắc để test không trở nên mong manh

Test kế thừa cần xác nhận hợp đồng công khai của flow thay vì phụ thuộc vào mọi chi tiết XML nội bộ. Một số nguyên tắc:

- Assertion vào flow ID, state, view, event, input, scope và kết quả nghiệp vụ mà caller hoặc người dùng thực sự quan sát được.
- Với cấu hình quan trọng như binder allowlist hoặc action count, thêm kiểm tra trực tiếp vì đây là ranh giới bảo mật và side effect.
- Không so sánh toàn bộ XML dưới dạng chuỗi; thứ tự attribute hoặc cách format không nói lên hành vi.
- Dùng mock hoặc fake service có kết quả xác định để test không phụ thuộc database, thời gian hoặc dịch vụ ngoài.
- Kiểm tra cả hành vi kế thừa cần giữ và hành vi mới được thêm; không chỉ kiểm tra nhánh mới.
- Khi chủ ý thay đổi hợp đồng, cập nhật assertion và ghi rõ vì sao hành vi cha không còn áp dụng cho child.

Không nên kiểm tra mọi thuộc tính nội bộ nếu chúng không ảnh hưởng hành vi. Tuy nhiên, những cấu hình có ảnh hưởng tới quyền bind, action side effect, dữ liệu scope hoặc xử lý lỗi cần có assertion rõ ràng.

## 12. Checklist trước khi chấp nhận thay đổi kế thừa

Trước khi đưa thay đổi flow cha/con vào nhánh chính, hãy rà soát:

1. Flow registry xây dựng được cả parent và child với đúng builder context.
2. Child flow được khởi chạy bằng ID riêng và nhận đủ input.
3. Các state kế thừa cần giữ vẫn tồn tại; state override dùng đúng view và model.
4. Transition cũ cần giữ vẫn hoạt động; transition mới đi tới state hợp lệ.
5. Action vòng đời và transition chạy đúng số lần, đúng thứ tự.
6. Binder allowlist, conversion và validation vẫn đúng với view con.
7. Scope chứa đúng dữ liệu qua các state và không lộ dữ liệu nhạy cảm.
8. Exception handler và nhánh phục hồi không bị thay đổi ngoài ý muốn.
9. Các flow con khác cùng kế thừa parent đã được chạy lại test liên quan.
10. CI có kiểm tra parse/build flow và flow execution test cho các hành trình quan trọng.

Kế thừa định nghĩa giúp tái sử dụng cấu hình, nhưng kết quả cần được xem như một hợp đồng hoàn chỉnh sau merge. Hãy kiểm tra cấu trúc flow con được registry xây dựng, rồi chạy các event quan trọng trên chính flow con. Khi cả phần kế thừa cần giữ và phần override mới đều có assertion, thay đổi ở flow cha hoặc flow con sẽ ít gây ra điều hướng, binding và side effect ngoài dự kiến.
