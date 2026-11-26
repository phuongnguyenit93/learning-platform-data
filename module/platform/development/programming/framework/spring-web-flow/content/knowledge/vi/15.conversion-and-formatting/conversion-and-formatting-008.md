# Chọn converter cho từng binding khi cần

Trong Spring Web Flow, dữ liệu nhập từ trình duyệt thường đi vào model của view-state thông qua cơ chế binding. Giá trị trên HTML thường là chuỗi, trong khi thuộc tính của model có thể là số, ngày tháng, enum hoặc một kiểu dữ liệu chuyên biệt. Framework cần chuyển đổi giữa hai dạng này trước khi ứng dụng xử lý nghiệp vụ và khi hiển thị dữ liệu trở lại view.

Conversion service có thể tự chọn converter phù hợp dựa trên kiểu nguồn và kiểu đích. Tuy nhiên, có trường hợp một thuộc tính cần cách chuyển đổi riêng: ngày theo định dạng địa phương, số tiền có dấu phân cách riêng, mã trạng thái theo quy ước của hệ thống hoặc chuỗi mã có cấu trúc. Khi đó, Spring Web Flow cho phép chỉ định converter ngay trên từng binding trong phần binder của view-state.

Bài học thuộc chương **Chuyển đổi và định dạng** của module **Spring Web Flow**. Module này hướng dẫn mô hình hóa hành trình web nhiều bước bằng state, event, transition và subflow; thực hành form binding, validation, quản lý scope và phiên, tích hợp Spring MVC, kiểm thử và phục hồi luồng khi gặp lỗi.

## 1. Binding và conversion trong một view-state

Binding kết nối trường dữ liệu trong view với thuộc tính của model. Ví dụ, form nhập hóa đơn có các trường:

- Số lượng: người dùng nhập chuỗi như 3.
- Đơn giá: người dùng nhập chuỗi như 1.250,50.
- Ngày lập hóa đơn: người dùng nhập chuỗi như 25/11/2026.
- Trạng thái: người dùng chọn một giá trị trong danh sách.

Model có thể định nghĩa các thuộc tính tương ứng là **Integer**, **BigDecimal**, **LocalDate** hoặc một enum. Trước khi gọi service nghiệp vụ, ứng dụng cần chuyển chuỗi nhận được thành đúng kiểu. Khi render, một số kiểu dữ liệu cũng cần được định dạng lại thành chuỗi dễ đọc.

Có thể hình dung quy trình như sau:

~~~mermaid
flowchart LR
    A["Giá trị từ HTML<br/>String"] --> B["Binder của view-state"]
    B --> C["Chọn converter"]
    C --> D["Thuộc tính model<br/>kiểu Java"]
    D --> E["Validation"]
    E --> F["Action / service nghiệp vụ"]
    F --> G["Model và view"]
    G --> H["Converter / định dạng"]
    H --> I["Giá trị hiển thị"]
~~~

Converter xử lý việc chuyển đổi biểu diễn và kiểu dữ liệu. Validation kiểm tra giá trị sau khi chuyển đổi có hợp lệ theo quy tắc của ứng dụng hay không. Hai công việc này liên quan nhưng không thay thế cho nhau.

Ví dụ, chuỗi 1.250,50 có thể được chuyển thành **BigDecimal** với giá trị 1250.50. Conversion thành công chưa có nghĩa số tiền được phép thanh toán; service vẫn phải kiểm tra số tiền dương, hạn mức, loại tiền và quyền thực hiện thao tác.

## 2. Converter mặc định và converter chỉ định cho binding

Khi không chỉ định converter trên binding, conversion service của Web Flow sẽ tìm converter phù hợp với kiểu nguồn và kiểu đích. Cách này phù hợp với các chuyển đổi phổ biến, có ý nghĩa nhất quán trong toàn ứng dụng, chẳng hạn chuyển chuỗi thành kiểu số hoặc boolean theo quy tắc đã đăng ký.

Khi một thuộc tính cần cách chuyển đổi đặc thù, có thể khai báo converter tường minh trong binder:

~~~xml
<view-state id="editInvoice" view="invoice/edit"
            model="invoiceForm">
    <binder>
        <binding property="quantity" />
        <binding property="unitPrice" converter="localizedDecimal" />
        <binding property="invoiceDate" converter="localizedDate" />
        <binding property="status" converter="invoiceStatus" />
    </binder>

    <transition on="save" to="review" />
    <transition on="cancel" to="cancelled" />
</view-state>
~~~

Trong ví dụ:

- quantity không chỉ định converter riêng, nên conversion service chọn converter phù hợp với kiểu thuộc tính.
- unitPrice dùng converter có định danh localizedDecimal.
- invoiceDate dùng converter localizedDate.
- status dùng converter invoiceStatus, nếu quy ước mã trạng thái của form khác cách chuyển đổi mặc định.

Giá trị trong thuộc tính converter là định danh converter đã được đăng ký với conversion service mà flow builder sử dụng. Tên localizedDecimal, localizedDate và invoiceStatus trong ví dụ là tên minh họa; ứng dụng cần đăng ký đúng các converter này trước khi flow được xây dựng.

Chỉ khai báo converter khi có lý do cụ thể. Nếu mọi thuộc tính kiểu Integer đều dùng cách chuyển đổi chuẩn của ứng dụng, để conversion service tự chọn sẽ giúp cấu hình gọn hơn. Nếu hai thuộc tính cùng kiểu Java nhưng có định dạng đầu vào khác nhau, chỉ định converter trên từng binding giúp thể hiện rõ quy tắc của từng trường.

## 3. Phân biệt converter theo binding với converter dùng chung

Converter có thể được chọn theo hai cách:

| Cách chọn | Phạm vi | Khi nên dùng |
|---|---|---|
| Tự chọn theo kiểu nguồn và đích | Các binding tương thích với kiểu dữ liệu và converter đã đăng ký | Chuyển đổi phổ biến, nhất quán |
| Chỉ định bằng thuộc tính converter của binding | Một thuộc tính trong binder của view-state | Định dạng hoặc quy ước riêng cho một trường |

Giả sử hai trường cùng có kiểu String trong model nhưng biểu diễn khác nhau:

- customerCode phải theo mẫu mã khách hàng của hệ thống.
- externalReference có thể chứa chuỗi tham chiếu do đối tác cấp.

Nếu ứng dụng cần kiểm tra hoặc chuẩn hóa hai giá trị theo hai quy tắc khác nhau, hãy dùng converter riêng cho từng binding hoặc để chúng là chuỗi và xác thực theo service. Không nên tạo một converter toàn cục cho mọi chuỗi chỉ vì một màn hình có định dạng đặc biệt.

Ngược lại, nếu cùng một định dạng ngày được dùng ở nhiều flow, converter dùng chung có thể là lựa chọn hợp lý. Quy tắc chung nên được cấu hình ở conversion service; ngoại lệ của một trường nên được chỉ định ở binder của view-state.

## 4. Đăng ký converter trong conversion service của Web Flow

Converter được chỉ định trong binder phải tồn tại trong conversion service mà flow builder sử dụng. Với cấu hình XML, ứng dụng có thể liên kết conversion service vào flow builder services:

~~~xml
<webflow:flow-registry id="flowRegistry"
                       base-path="/WEB-INF/flows">
    <webflow:flow-builder-services
        conversion-service="webFlowConversionService" />
</webflow:flow-registry>
~~~

webFlowConversionService là bean conversion service do ứng dụng cấu hình. Bean này cần chứa converter mặc định và các converter tùy chỉnh mà flow sử dụng. Tên bean trong ví dụ là tên do ứng dụng đặt; cách khởi tạo và đăng ký converter cụ thể phụ thuộc API của phiên bản Spring Web Flow và thư viện binding đang dùng.

Quy trình cấu hình gồm:

1. Xác định kiểu dữ liệu nguồn từ request và kiểu đích trong model.
2. Chọn cách chuyển đổi cần áp dụng, bao gồm quy tắc locale, null và lỗi parse.
3. Cài đặt converter phù hợp theo contract của conversion service đang sử dụng.
4. Đăng ký converter với định danh ổn định, ví dụ localizedDate.
5. Cấu hình flow builder dùng conversion service đó.
6. Chỉ định định danh converter trong binding cần áp dụng.
7. Khởi động ứng dụng và kiểm tra converter được tìm thấy khi flow được khởi tạo.

Không nên nhầm conversion service của Spring Web Flow với mọi bean có tên conversionService trong Spring application context. Ứng dụng có thể có nhiều tầng binding khác nhau. Hãy bảo đảm bean được gắn vào đúng FlowBuilderServices hoặc điểm cấu hình tương ứng của phiên bản đang sử dụng.

## 5. Ví dụ chọn converter cho ngày và số tiền

Một biểu mẫu hóa đơn có thể nhận ngày theo định dạng dd/MM/yyyy và số tiền theo quy ước dấu phẩy thập phân của một locale. Hai trường này cần converter rõ ràng để dữ liệu được hiểu thống nhất.

Binder:

~~~xml
<view-state id="editInvoice" view="invoice/edit"
            model="invoiceForm">
    <binder>
        <binding property="invoiceDate" converter="localizedDate" />
        <binding property="unitPrice" converter="localizedDecimal" />
        <binding property="quantity" />
    </binder>

    <transition on="save" to="review" />
</view-state>
~~~

View JSP:

~~~jsp
<form:form modelAttribute="invoiceForm"
           action="${flowExecutionUrl}"
           method="post">
    <label for="invoiceDate">Ngày hóa đơn</label>
    <form:input path="invoiceDate" id="invoiceDate" />

    <label for="unitPrice">Đơn giá</label>
    <form:input path="unitPrice" id="unitPrice" />

    <label for="quantity">Số lượng</label>
    <form:input path="quantity" id="quantity" />

    <button type="submit" name="_eventId_save">Lưu</button>
</form:form>
~~~

Giả sử người dùng nhập:

| Trường | Chuỗi từ trình duyệt | Giá trị model mong muốn |
|---|---|---|
| Ngày hóa đơn | 25/11/2026 | Ngày 25 tháng 11 năm 2026 |
| Đơn giá | 1.250,50 | BigDecimal có giá trị 1250.50 |
| Số lượng | 3 | Integer có giá trị 3 |

Converter ngày phải biết chính xác định dạng ngày được chấp nhận. Converter số tiền phải biết locale và quy ước dấu phân cách. Không nên đoán locale dựa trên dấu chấm hoặc dấu phẩy trong chuỗi, vì cùng một chuỗi có thể mang ý nghĩa khác nhau ở các vùng.

Với số tiền, nên dùng BigDecimal để tránh sai số nhị phân của double. Nếu nghiệp vụ có nhiều loại tiền, cần giữ cả mã tiền tệ trong model và xác định rõ quy tắc làm tròn. Một converter chỉ chuyển chuỗi thành số thập phân không thể tự suy ra đơn vị tiền tệ một cách an toàn.

## 6. Converter một chiều và chuyển đổi hai chiều

Binding thường cần chuyển dữ liệu từ request vào model. Khi render view, ứng dụng cũng có thể cần biểu diễn giá trị model thành chuỗi. Vì vậy, hãy xác định converter cần hỗ trợ một hay cả hai chiều.

| Hướng chuyển đổi | Ví dụ | Câu hỏi cần giải quyết |
|---|---|---|
| Chuỗi sang model | 25/11/2026 thành ngày | Chuỗi nào được chấp nhận? |
| Model sang chuỗi | Ngày thành 25/11/2026 | Hiển thị theo định dạng nào? |
| Hai chiều | 1.250,50 thành BigDecimal và ngược lại | Giá trị hiển thị có thể parse lại nhất quán không? |

Một converter hai chiều cần có quy tắc rõ ràng cho cả parse và format. Nếu chuỗi được render ra không thể parse lại, người dùng có thể gặp lỗi khi gửi lại form mà không thay đổi trường đó.

Ví dụ logic chuyển đổi số tiền ở mức khái niệm:

~~~java
BigDecimal parseAmount(String text, Locale locale) {
    NumberFormat format = NumberFormat.getNumberInstance(locale);
    format.setParseBigDecimal(true);

    ParsePosition position = new ParsePosition(0);
    String input = text.trim();
    Number parsed = format.parse(input, position);

    if (!(parsed instanceof BigDecimal) || position.getIndex() != input.length()) {
        throw new IllegalArgumentException("Định dạng số tiền không hợp lệ");
    }

    return (BigDecimal) parsed;
}

String formatAmount(BigDecimal amount, Locale locale) {
    NumberFormat format = NumberFormat.getNumberInstance(locale);
    format.setMinimumFractionDigits(2);
    format.setMaximumFractionDigits(2);
    return format.format(amount);
}
~~~

Đây là phần logic minh họa cho parse và format; cần bọc nó bằng contract converter của conversion service mà ứng dụng đang sử dụng. Đoạn code không phải một implementation trực tiếp của interface converter trong mọi phiên bản Spring Web Flow.

Trong code thực tế, hãy xử lý rõ chuỗi rỗng, khoảng trắng, dấu âm, số chữ số thập phân, overflow và ký tự thừa. Đừng chấp nhận chuỗi có phần đuôi không parse được chỉ vì phần đầu đã tạo ra một số hợp lệ.

## 7. Locale, timezone và quy ước định dạng

Ngày và số là hai nhóm dữ liệu dễ bị hiểu sai khi ứng dụng phục vụ người dùng ở nhiều locale.

**Với số:**

- Dấu chấm có thể là dấu phân nhóm hàng nghìn hoặc dấu thập phân tùy locale.
- Dấu phẩy cũng có thể có hai ý nghĩa tương tự.
- Số âm, số phần trăm và ký hiệu tiền tệ có quy tắc riêng.
- Giá trị model nên giữ kiểu số chính xác; chỉ định dạng khi hiển thị.

**Với ngày và thời gian:**

- Ngày lịch như ngày sinh hoặc ngày hóa đơn thường không cần timezone.
- Thời điểm như lúc thanh toán hoặc lúc ghi nhận sự kiện cần xác định timezone hoặc quy ước lưu trữ, thường lưu theo một chuẩn thống nhất rồi chuyển khi hiển thị.
- Chuỗi ngày nên dùng một định dạng được công bố rõ ràng; không phụ thuộc vào locale mặc định của máy chủ.
- Cần kiểm tra ngày không tồn tại, ví dụ ngày 31 của một tháng chỉ có 30 ngày.

Nếu ứng dụng cho phép người dùng chọn ngôn ngữ hoặc locale, converter cần nhận locale từ ngữ cảnh phù hợp thay vì giữ một locale toàn cục cố định. Với converter được chia sẻ giữa nhiều request, không lưu trạng thái mutable theo từng người dùng trong instance dùng chung.

## 8. Conversion error khác validation error

Conversion error xảy ra khi không thể chuyển biểu diễn đầu vào thành kiểu dữ liệu đích. Validation error xảy ra khi giá trị đã chuyển đổi được nhưng không thỏa quy tắc nghiệp vụ.

Ví dụ:

| Đầu vào | Conversion | Validation |
|---|---|---|
| abc cho trường số tiền | Lỗi vì không parse được số | Chưa tới bước kiểm tra hạn mức |
| -10,00 cho trường số tiền | Có thể chuyển thành BigDecimal | Lỗi vì số tiền phải lớn hơn 0 |
| 31/02/2026 cho ngày | Lỗi vì ngày không tồn tại | Chưa tới bước kiểm tra ngày có nằm trong kỳ hóa đơn không |
| Ngày hợp lệ nhưng nằm ngoài kỳ cho phép | Chuyển đổi thành công | Lỗi theo quy tắc nghiệp vụ |

Khi conversion thất bại, view cần hiển thị thông báo gắn với trường để người dùng sửa dữ liệu. Khi conversion thành công nhưng validation thất bại, ứng dụng hiển thị lỗi nghiệp vụ tương ứng. Không nên bắt mọi lỗi rồi thay bằng giá trị mặc định như 0 hoặc ngày hiện tại, vì điều đó che giấu dữ liệu đầu vào không hợp lệ.

Một converter tốt nên cung cấp thông tin lỗi đủ để ứng dụng hiển thị thông báo dễ hiểu, nhưng không đưa stack trace hoặc chi tiết nội bộ lên giao diện. Nếu cần thông báo thân thiện, hãy ánh xạ lỗi conversion sang message code và message resource theo cấu hình của ứng dụng.

## 9. Khi nào nên chọn converter riêng cho một binding?

Hãy chỉ định converter riêng khi cách chuyển đổi của thuộc tính đó khác quy tắc mặc định hoặc khác các thuộc tính cùng kiểu.

Các trường hợp thường gặp:

- Một trường ngày nhận dd/MM/yyyy, trong khi trường khác nhận định dạng ISO.
- Một trường số tiền cần locale cụ thể, còn một trường tỷ lệ phần trăm có quy tắc khác.
- Mã enum trong form dùng token ổn định như PENDING, nhưng giao diện hiển thị nhãn tiếng Việt.
- Một giá trị có cấu trúc cần parse theo định dạng nghiệp vụ đã công bố.
- Hai thuộc tính cùng kiểu Java nhưng cần chuẩn hóa đầu vào theo quy tắc riêng.

Không nên dùng converter riêng nếu conversion service đã có converter mặc định phù hợp. Cũng không nên đưa các quy tắc nghiệp vụ phức tạp vào converter. Ví dụ, converter có thể parse mã khách hàng thành một giá trị có cấu trúc, nhưng việc khách hàng có được phép xem hóa đơn hay không phải do service nghiệp vụ kiểm tra.

Converter nên tập trung vào chuyển đổi biểu diễn, không truy cập database theo mỗi trường binding, không tạo giao dịch và không thực hiện tác động nghiệp vụ. Điều này giúp converter dễ kiểm thử, có thể dùng lại và tránh side effect khi framework bind hoặc render view.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ định converter ID chưa đăng ký | Flow không tìm thấy converter khi binding | Đăng ký converter trong đúng conversion service |
| Dùng một converter cho các trường có quy tắc khác nhau | Parse sai hoặc hiển thị không nhất quán | Chọn converter riêng theo binding |
| Chỉ kiểm tra parse mà không kiểm tra phần chuỗi còn lại | Chấp nhận đầu vào có ký tự thừa | Xác nhận toàn bộ chuỗi đã được tiêu thụ |
| Dùng double cho số tiền | Sai số làm tròn | Dùng BigDecimal và quy tắc scale rõ ràng |
| Dùng locale mặc định của máy chủ | Kết quả khác nhau giữa môi trường | Truyền locale có chủ đích |
| Dùng converter để kiểm tra quyền hoặc trạng thái nghiệp vụ | Trộn trách nhiệm và khó kiểm soát side effect | Để service nghiệp vụ kiểm tra |
| Converter dùng chung giữ state mutable theo request | Request đồng thời có thể ảnh hưởng lẫn nhau | Thiết kế converter stateless hoặc an toàn luồng |
| Chuyển chuỗi rỗng thành giá trị mặc định tùy tiện | Che giấu lỗi nhập liệu | Xác định rõ chính sách null/empty và báo lỗi phù hợp |
| Không kiểm thử chiều format | Giá trị render ra không gửi lại được | Kiểm thử round-trip hai chiều |

## 11. Kiểm thử converter và binding

Converter cần được kiểm thử độc lập, sau đó kiểm thử qua flow để xác nhận binder thực sự sử dụng converter đã chỉ định.

| Nhóm kiểm thử | Nội dung |
|---|---|
| Parse hợp lệ | Chuỗi đúng định dạng chuyển thành kiểu model mong muốn |
| Parse không hợp lệ | Chuỗi sai, thiếu, thừa ký tự hoặc ngày không tồn tại tạo lỗi rõ ràng |
| Format | Giá trị model được hiển thị theo đúng locale và định dạng |
| Round-trip | Parse(format(value)) giữ nguyên giá trị theo độ chính xác đã quy định |
| Null và empty | Chuỗi rỗng, null và khoảng trắng tuân theo chính sách thống nhất |
| Locale | Dấu thập phân và phân nhóm được xử lý đúng với từng locale hỗ trợ |
| Binding theo thuộc tính | Mỗi binding gọi đúng converter đã cấu hình |
| Validation | Giá trị parse được nhưng vi phạm nghiệp vụ vẫn bị từ chối |
| Request đồng thời | Converter dùng chung không làm rò rỉ trạng thái giữa các request |

Ví dụ các ca kiểm thử cho converter số tiền:

~~~java
@Test
void parsesVietnameseDecimal() {
    BigDecimal amount = parseAmount("1.250,50", Locale.forLanguageTag("vi-VN"));

    assertEquals(new BigDecimal("1250.50"), amount);
}

@Test
void rejectsTrailingCharacters() {
    assertThrows(
        IllegalArgumentException.class,
        () -> parseAmount("1250,50abc", Locale.forLanguageTag("vi-VN"))
    );
}
~~~

Đây là ví dụ kiểm thử cho hàm chuyển đổi minh họa ở trên. Với converter thực tế, hãy kiểm thử qua adapter và conversion service mà Spring Web Flow đang dùng, sau đó chạy một flow test để xác nhận lỗi binding được trả về đúng view-state.

Một kiểm thử tích hợp nên gửi form có một trường hợp lệ và một trường không hợp lệ, xác nhận các lỗi được gắn đúng thuộc tính, view vẫn hiển thị được và người dùng có thể sửa rồi gửi lại. Cũng nên kiểm tra trường hợp converter bị thiếu đăng ký để phát hiện lỗi cấu hình ngay khi khởi tạo ứng dụng hoặc flow.

## 12. Quy trình lựa chọn converter cho một binding

Khi cấu hình binder cho view-state, hãy lần lượt trả lời:

1. Kiểu dữ liệu nguồn từ request là gì và kiểu đích trong model là gì?
2. Conversion service hiện tại đã có converter phù hợp chưa?
3. Thuộc tính này có định dạng hoặc quy tắc khác với các thuộc tính cùng kiểu không?
4. Nếu cần converter riêng, converter ID nào được đăng ký trong conversion service của FlowBuilderServices?
5. Converter có cần hỗ trợ cả parse và format không?
6. Locale, timezone, null, empty và độ chính xác được xử lý thế nào?
7. Conversion error được hiển thị ra sao và validation nghiệp vụ được thực hiện ở đâu?
8. Các trường hợp hợp lệ, không hợp lệ, round-trip và request đồng thời đã được kiểm thử chưa?

Chỉ định converter trên binding giúp view-state diễn đạt rõ cách chuyển đổi của từng thuộc tính, trong khi conversion service vẫn cung cấp các quy tắc dùng chung. Khi phân biệt conversion với validation, xử lý locale có chủ đích và kiểm thử cả hai chiều cần thiết, form binding trong Spring Web Flow sẽ dễ dự đoán, dễ bảo trì và ít gây lỗi dữ liệu hơn.
