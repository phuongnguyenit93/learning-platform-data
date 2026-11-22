# Tương thích ngược và tương thích xuôi theo góc nhìn bên cung cấp và bên sử dụng

Khi một thư viện Java, một dịch vụ hoặc một giao thức được nâng cấp, hai phía thường không được triển khai cùng lúc. Bên cung cấp có thể đã chạy phiên bản mới trong khi ứng dụng của khách hàng vẫn dùng phiên bản cũ; hoặc ứng dụng được cập nhật trước nhưng dịch vụ phía sau chưa thể nâng cấp. Vì vậy, câu hỏi quan trọng không chỉ là phiên bản mới có chạy được hay không, mà là **hai phía ở những phiên bản khác nhau có tiếp tục giao tiếp đúng hợp đồng hay không**.

Tương thích ngược và tương thích xuôi mô tả khả năng phối hợp giữa các phiên bản theo một chiều thời gian. Hai khái niệm này cần được xác định rõ đang nhìn từ bên cung cấp hay bên sử dụng. Cùng một cặp phiên bản có thể được gọi là tương thích ngược ở phía này và tương thích xuôi ở phía kia.

## 1. Xác định bên cung cấp, bên sử dụng và phiên bản

Trong bài này, **bên cung cấp** (provider) là thành phần công bố API, thư viện, dịch vụ hoặc định dạng dữ liệu. **Bên sử dụng** (consumer) là thành phần gọi API, phụ thuộc thư viện, gửi yêu cầu hoặc đọc dữ liệu do bên cung cấp tạo ra.

Ví dụ:

- Một thư viện Java cung cấp lớp và phương thức công khai; ứng dụng Spring Boot phụ thuộc thư viện đó là bên sử dụng.
- Một REST service cung cấp endpoint; ứng dụng mobile hoặc một service khác gọi endpoint là bên sử dụng.
- Một chương trình ghi dữ liệu vào file là bên cung cấp dữ liệu; chương trình đọc file ở lần chạy sau là bên sử dụng dữ liệu.
- Một module công bố interface; module khác triển khai interface đó. Trong trường hợp này cần xác định rõ ai định nghĩa hợp đồng và ai chịu trách nhiệm triển khai.

Ký hiệu:

- **P1**: phiên bản 1 của bên cung cấp.
- **P2**: phiên bản 2 của bên cung cấp.
- **C1**: phiên bản 1 của bên sử dụng.
- **C2**: phiên bản 2 của bên sử dụng.

P1/C1 là cặp phiên bản cũ. P2/C2 là cặp phiên bản mới. Khi nâng cấp độc lập, hệ thống có thể xuất hiện hai tổ hợp trung gian: P2 chạy với C1 hoặc P1 chạy với C2. Hai tổ hợp này là trọng tâm khi đánh giá tương thích.

Hợp đồng giữa hai bên không chỉ gồm tên endpoint hay chữ ký phương thức. Nó còn có thể bao gồm kiểu dữ liệu, quy tắc validation, giá trị mặc định, thứ tự xử lý, mã lỗi, ngoại lệ, định dạng serialization, yêu cầu xác thực, giới hạn kích thước và ý nghĩa nghiệp vụ. Một thay đổi chỉ an toàn khi nó giữ được các cam kết mà phía còn lại đang dựa vào.

## 2. Tương thích khi nhìn từ bên cung cấp

Bên cung cấp thường phát hành phiên bản mới trong khi không thể buộc tất cả bên sử dụng nâng cấp ngay. Do đó, câu hỏi ở phía cung cấp là: phiên bản mới có tiếp tục phục vụ được những consumer đã được xây dựng theo hợp đồng cũ không?

### 2.1. Tương thích ngược của bên cung cấp

**P2 tương thích ngược với C1** khi provider phiên bản mới vẫn hỗ trợ những cách sử dụng hợp lệ mà consumer phiên bản cũ đang thực hiện.

Ví dụ, thư viện phiên bản 1 có phương thức:

~~~java
public class PriceCalculator {
    public BigDecimal total(BigDecimal price) {
        return price;
    }
}
~~~

Ứng dụng đã biên dịch dựa vào phương thức `total(BigDecimal)`. Nếu phiên bản 2 xóa phương thức đó và chỉ giữ `total(BigDecimal, Currency)`, ứng dụng cũ có thể gặp `NoSuchMethodError` khi chạy với JAR mới. Việc thư viện phiên bản 2 tự biên dịch thành công không chứng minh rằng binary của ứng dụng cũ còn tương thích.

Một cách nâng cấp ít gây gián đoạn hơn là giữ phương thức cũ và chuyển tiếp sang cách triển khai mới:

~~~java
public class PriceCalculator {
    public BigDecimal total(BigDecimal price) {
        return total(price, Currency.getInstance("VND"));
    }

    public BigDecimal total(BigDecimal price, Currency currency) {
        // Tính tổng theo currency được chỉ định.
        return price;
    }
}
~~~

Ví dụ này chỉ an toàn nếu quy tắc mặc định thực sự phù hợp với ý nghĩa cũ của API. Giữ nguyên chữ ký nhưng đổi cách tính, đơn vị tiền tệ hoặc tác dụng phụ vẫn có thể phá vỡ hợp đồng ở mức hành vi.

Ở API HTTP, P2 có thể bổ sung một trường phản hồi tùy chọn. Consumer cũ thường tiếp tục hoạt động nếu nó bỏ qua trường chưa biết và các trường cũ vẫn giữ nguyên ý nghĩa. Ngược lại, nếu P2 đổi tên trường cũ, đổi kiểu dữ liệu hoặc bắt buộc consumer phải gửi thêm một trường mới, thay đổi đó có thể phá vỡ C1.

### 2.2. Tương thích xuôi của bên cung cấp

**P1 tương thích xuôi với C2** khi provider phiên bản cũ vẫn có thể phục vụ consumer phiên bản mới trong phạm vi tính năng mà provider cũ hỗ trợ.

Điều này thường đòi hỏi giao thức có khả năng mở rộng. Chẳng hạn, P1 có thể bỏ qua trường yêu cầu tùy chọn mà nó chưa biết, hoặc trả về thông tin cho phép C2 nhận ra một tính năng chưa được hỗ trợ. Nếu C2 gửi một thao tác mới mà P1 hoàn toàn không có, hai bên không thể tự tạo ra khả năng đó; consumer phải có phương án dự phòng hoặc thông báo tính năng không khả dụng.

Tương thích xuôi ở phía provider vì vậy không có nghĩa provider cũ phải thực hiện được mọi chức năng của phiên bản tương lai. Nó có nghĩa provider cũ xử lý an toàn những tương tác có thể hiểu được, đồng thời biểu đạt rõ giới hạn đối với chức năng mới.

## 3. Tương thích khi nhìn từ bên sử dụng

Consumer cũng có vòng đời phát hành riêng. Một ứng dụng mới có thể cần kết nối tới dịch vụ cũ vì môi trường triển khai chưa nâng cấp đồng bộ; một ứng dụng cũ có thể tiếp tục chạy trong thời gian dài sau khi dịch vụ đã được nâng cấp.

### 3.1. Tương thích ngược của bên sử dụng

**C2 tương thích ngược với P1** khi consumer phiên bản mới vẫn có thể sử dụng provider phiên bản cũ.

Ví dụ, ứng dụng C2 được phát hành với một thư viện mới hơn, nhưng một số môi trường vẫn đang chạy dịch vụ P1. C2 cần tiếp tục dùng được các endpoint và trường dữ liệu đã có ở P1. Nếu C2 gọi ngay endpoint chỉ xuất hiện ở P2 trong lúc khởi động, nó sẽ không hoạt động với môi trường cũ.

Một consumer có thể hỗ trợ trường hợp này bằng cách:

- Chỉ yêu cầu chức năng nền tảng mà P1 đã cung cấp.
- Kiểm tra capability hoặc phiên bản API trước khi gọi tính năng mới.
- Xử lý trường dữ liệu tùy chọn bị thiếu bằng giá trị mặc định có ý nghĩa.
- Có phương án dự phòng khi provider chưa hỗ trợ một thao tác mới.

Trong ứng dụng Java, điều này cũng xuất hiện khi nâng cấp dependency. Nếu ứng dụng mới gọi phương thức chỉ có trong phiên bản thư viện mới, ứng dụng không thể chạy với JAR cũ. Muốn hỗ trợ cả hai phiên bản, consumer phải giới hạn mình ở API chung hoặc kiểm tra khả năng trước khi sử dụng phần mở rộng.

### 3.2. Tương thích xuôi của bên sử dụng

**C1 tương thích xuôi với P2** khi consumer phiên bản cũ vẫn xử lý được provider phiên bản mới.

Một ví dụ phổ biến là P2 bổ sung trường `status` vào JSON response. C1 có thể tiếp tục hoạt động nếu parser chấp nhận trường không biết và logic nghiệp vụ không phụ thuộc vào trường mới. Nếu C1 từ chối mọi trường chưa khai báo hoặc giả định response luôn có đúng một tập trường cố định, việc bổ sung có thể làm C1 lỗi dù P2 vẫn giữ tất cả trường cũ.

Consumer cũng cần chuẩn bị cho dữ liệu có giá trị mới. Ví dụ, P2 bổ sung một trạng thái đơn hàng mới. Nếu C1 chuyển mọi giá trị enum thành một enum Java cố định và ném lỗi khi gặp giá trị chưa biết, C1 không còn tương thích xuôi. Có thể thiết kế một nhánh `UNKNOWN` hoặc giữ lại giá trị gốc để xử lý an toàn, tùy yêu cầu nghiệp vụ.

Khả năng bỏ qua dữ liệu chưa biết cần được áp dụng có chủ đích. Consumer không nên bỏ qua trường có ý nghĩa bảo mật, quyền truy cập, số tiền hoặc trạng thái giao dịch nếu việc bỏ qua có thể khiến nó đưa ra quyết định sai. Tương thích xuôi phải đi cùng quy tắc an toàn và xử lý lỗi rõ ràng.

## 4. Đặt hai góc nhìn cạnh nhau

Hai tổ hợp phiên bản cho thấy vì sao phải nêu rõ góc nhìn khi dùng thuật ngữ:

| Tổ hợp đang chạy | Góc nhìn bên cung cấp | Góc nhìn bên sử dụng | Câu hỏi cần trả lời |
|---|---|---|---|
| P2 + C1 | Provider tương thích ngược | Consumer tương thích xuôi | Provider mới có tiếp tục phục vụ consumer cũ không? |
| P1 + C2 | Provider tương thích xuôi | Consumer tương thích ngược | Consumer mới có tiếp tục dùng được provider cũ không? |

Có thể ghi nhớ bằng sơ đồ:

~~~text
P2 (provider mới)  <---->  C1 (consumer cũ)
  tương thích ngược          tương thích xuôi

P1 (provider cũ)  <---->  C2 (consumer mới)
  tương thích xuôi          tương thích ngược
~~~

Tên gọi trong tài liệu kỹ thuật đôi khi thay đổi theo đối tượng được xem là đang nâng cấp. Vì vậy, trong tài liệu migration, review hoặc hợp đồng tích hợp, nên ghi cả cặp phiên bản cụ thể, ví dụ `P2 + C1`, thay vì chỉ ghi “backward compatible”. Cách ghi này loại bỏ phần lớn sự mơ hồ.

## 5. Các lớp tương thích cần kiểm tra trong Java

Một thay đổi có thể tương thích ở một lớp nhưng không tương thích ở lớp khác. Biên dịch thành công chỉ là một loại bằng chứng; nó không chứng minh ứng dụng cũ sẽ liên kết, chạy và cho kết quả đúng.

### 5.1. Tương thích mã nguồn (source compatibility)

Mã nguồn cũ có thể biên dịch lại với phiên bản mới của thư viện hoặc JDK mà không cần sửa đổi hay không?

Các thay đổi có thể làm mã nguồn không còn biên dịch:

- Xóa hoặc đổi tên lớp, phương thức, constructor hay field công khai.
- Đổi kiểu tham số hoặc kiểu trả về khiến lời gọi cũ không còn hợp lệ.
- Thêm overload làm một lời gọi vốn rõ ràng trở nên mơ hồ.
- Thay đổi checked exception theo cách buộc caller phải xử lý thêm.
- Thêm phương thức abstract vào interface mà các lớp triển khai hiện tại chưa cài đặt.

Một thay đổi overload có thể gây lỗi source compatibility dù bytecode đã biên dịch trước đó vẫn liên kết được với phương thức cũ. Vì thế, cần kiểm tra cả tình huống biên dịch lại consumer lẫn tình huống chạy binary cũ.

### 5.2. Tương thích nhị phân (binary compatibility)

Bytecode đã biên dịch trước đó có thể liên kết và chạy với phiên bản thư viện mới mà không cần biên dịch lại hay không?

Bytecode lưu các tham chiếu tới lớp, phương thức và field theo tên cùng descriptor. Khi runtime không tìm thấy thành phần mà bytecode yêu cầu, chương trình có thể lỗi lúc liên kết hoặc khi đường chạy đó được thực thi. Ví dụ thường gặp là `NoSuchMethodError` khi phương thức đã bị xóa hoặc descriptor không còn khớp; `NoSuchFieldError` khi field được tham chiếu không còn tồn tại; và `IncompatibleClassChangeError` khi cấu trúc hoặc cách sử dụng kiểu thay đổi không tương thích.

Một ví dụ khác liên quan đến interface: thêm một phương thức abstract có thể khiến lớp triển khai cũ không có phần cài đặt tương ứng. Lời gọi phương thức đó trên đối tượng cũ có thể dẫn đến `AbstractMethodError`. Phương thức `default` có thể giảm rủi ro về binary compatibility trong một số trường hợp, nhưng vẫn phải xem xét xung đột giữa các interface và ý nghĩa hành vi của phần triển khai mặc định.

### 5.3. Tương thích hành vi (behavioral compatibility)

API vẫn có cùng chữ ký và ứng dụng vẫn chạy, nhưng kết quả hoặc tác dụng quan sát được có thay đổi không?

Ví dụ:

- Một phương thức trước đây chấp nhận giá trị `null`, phiên bản mới lại ném `NullPointerException`.
- Một truy vấn trước đây trả về danh sách đã sắp xếp, phiên bản mới trả về thứ tự không xác định.
- Một thao tác trước đây đồng bộ, phiên bản mới chuyển sang xử lý bất đồng bộ.
- Một lỗi nghiệp vụ trước đây trả về mã lỗi A, phiên bản mới trả về mã lỗi B.
- Một giá trị mặc định, quy tắc làm tròn hoặc cách tính thuế bị thay đổi.

Đây là lý do không thể kết luận tương thích chỉ bằng cách so sánh chữ ký API hoặc chạy kiểm tra biên dịch. Cần đối chiếu hành vi thực tế với hợp đồng và kỳ vọng của consumer.

### 5.4. Tương thích dữ liệu và giao thức

Consumer có đọc được dữ liệu đã được tạo bởi phiên bản cũ hoặc phiên bản mới không? Provider có hiểu được yêu cầu từ consumer ở phiên bản khác không?

Với JSON, các tình huống quan trọng gồm trường mới được thêm, trường cũ bị thiếu, trường đổi kiểu, giá trị enum mới và trường không còn được gửi. Với Java serialization hoặc dữ liệu lưu lâu dài, cần xem xét định danh lớp, cấu trúc dữ liệu, quy tắc chuyển đổi và khả năng đọc lại dữ liệu đã ghi từ phiên bản trước.

Không nên xem việc thêm trường là luôn an toàn. Trường mới có thể phá vỡ consumer dùng parser nghiêm ngặt; trường cũ có thể bị consumer mới coi là bắt buộc; hoặc hai bên có thể hiểu khác nhau về đơn vị và ý nghĩa của cùng một giá trị.

### 5.5. Tương thích nền tảng chạy và build

Trong migration Java, phiên bản JDK, mức bytecode, Gradle/Maven, plugin và dependency cũng là một phần của khả năng tương thích. Thư viện có thể tương thích về API nhưng yêu cầu JDK cao hơn môi trường chạy của consumer. Ngược lại, ứng dụng có thể biên dịch với JDK mới nhưng không chạy được trên runtime cũ do bytecode hoặc API nền tảng không được hỗ trợ.

Vì vậy, cần ghi riêng mức Java tối thiểu để biên dịch, mức Java tối thiểu để chạy và phiên bản công cụ build được hỗ trợ. Không nên gộp các điều kiện này thành một nhận xét chung như “hỗ trợ Java 21” nếu chưa nói rõ hỗ trợ ở giai đoạn nào.

## 6. Thiết kế provider để hỗ trợ nhiều thế hệ consumer

Provider có thể giảm rủi ro migration bằng cách quản lý hợp đồng công khai như một sản phẩm có vòng đời:

1. **Ưu tiên mở rộng có tính tùy chọn.** Thêm endpoint hoặc phương thức mới thường dễ phối hợp hơn việc đổi tên hoặc xóa thành phần cũ. Trường mới nên có quy tắc mặc định rõ ràng nếu consumer cũ không gửi hoặc không đọc nó.
2. **Giữ API cũ trong thời gian chuyển tiếp.** Có thể đánh dấu phương thức cũ là `@Deprecated`, cung cấp phương thức thay thế và để phương thức cũ ủy quyền sang phần triển khai mới khi ngữ nghĩa cho phép.
3. **Không đổi ý nghĩa âm thầm.** Giữ nguyên chữ ký nhưng đổi đơn vị, quy tắc validation, thứ tự hoặc tác dụng phụ vẫn là thay đổi hợp đồng.
4. **Công bố capability và giới hạn.** Consumer cần biết provider hỗ trợ chức năng nào, phiên bản nào hoặc định dạng nào. Có thể dùng endpoint discovery, metadata, header phiên bản hoặc cơ chế thương lượng phù hợp với hệ thống.
5. **Có chính sách deprecation và removal.** Nêu rõ phần nào sắp bị loại bỏ, phiên bản thay thế, khoảng thời gian chuyển đổi và thời điểm ngừng hỗ trợ.
6. **Kiểm tra với consumer đại diện.** Chạy contract test hoặc integration test với các phiên bản consumer còn được hỗ trợ, bao gồm binary cũ khi đó là yêu cầu thực tế.

Không phải mọi thay đổi đều có thể tương thích vô thời hạn. Nếu cần thay đổi không tương thích, provider nên tạo một ranh giới phiên bản rõ ràng, công bố lộ trình và cho phép hai hợp đồng cùng tồn tại trong khoảng thời gian chuyển đổi.

## 7. Thiết kế consumer để chịu được thay đổi có kiểm soát

Consumer không kiểm soát được thời điểm mọi provider nâng cấp. Vì vậy, consumer nên xác định rõ phiên bản thấp nhất và cao nhất mà nó hỗ trợ, rồi xử lý khác biệt có chủ đích:

1. **Phụ thuộc vào hợp đồng đã công bố.** Tránh gọi API nội bộ hoặc dựa vào chi tiết triển khai chưa được cam kết.
2. **Xử lý dữ liệu mở rộng.** Có thể bỏ qua trường không liên quan, lưu lại giá trị chưa biết hoặc ánh xạ enum mới sang trạng thái dự phòng. Với dữ liệu ảnh hưởng đến tiền, quyền, bảo mật hay trạng thái giao dịch, phải có quy tắc xử lý nghiệp vụ rõ ràng.
3. **Không giả định tính năng mới luôn có mặt.** Kiểm tra capability hoặc xử lý lỗi “không hỗ trợ” trước khi sử dụng tính năng mới.
4. **Đặt giá trị mặc định có ý nghĩa.** Khi provider cũ không gửi trường mới, consumer chỉ nên tự điền mặc định nếu mặc định đó đúng về nghiệp vụ.
5. **Tránh phụ thuộc vào chi tiết không ổn định.** Không dựa vào thứ tự JSON, thứ tự phần tử nếu hợp đồng không cam kết, thông báo lỗi tự do hoặc cách sắp xếp tình cờ.
6. **Kiểm thử với nhiều phiên bản provider.** Consumer mới cần được kiểm tra với provider cũ nhất còn hỗ trợ và provider mới nhất trong ma trận tương thích.

“Bỏ qua thứ chưa biết” không phải quy tắc áp dụng cho mọi trường. Nếu một trường mới biểu thị yêu cầu xác thực bổ sung, điều kiện pháp lý hoặc trạng thái không được phép, bỏ qua nó có thể tạo ra lỗi nghiêm trọng. Consumer phải phân biệt dữ liệu mở rộng có thể bỏ qua với dữ liệu bắt buộc phải hiểu.

## 8. Lập ma trận tương thích khi migration

Trước khi triển khai, hãy liệt kê các phiên bản provider và consumer có thể cùng tồn tại. Một ma trận nhỏ giúp biến nhận định chung thành các trường hợp có thể kiểm thử.

| Provider | Consumer | Mục tiêu kiểm tra |
|---|---|---|
| P1 | C1 | Baseline: xác nhận cặp đang hoạt động trước migration |
| P2 | C1 | Provider mới phục vụ consumer cũ |
| P1 | C2 | Consumer mới sử dụng provider cũ |
| P2 | C2 | Cặp phiên bản mới hoạt động đầy đủ |

Không phải hệ thống nào cũng cần hỗ trợ cả bốn tổ hợp. Ma trận cần phản ánh cách triển khai thực tế, thời gian rollback, các phiên bản còn được hỗ trợ và mức độ quan trọng của từng tích hợp. Nếu triển khai luôn đồng bộ và không có consumer cũ tồn tại, một số tổ hợp có thể nằm ngoài phạm vi; quyết định đó cần được ghi rõ.

Một quy trình migration thường có ba giai đoạn:

**Mở rộng (expand):** Provider bổ sung API hoặc trường mới theo cách vẫn giữ hợp đồng cũ. Consumer chưa cần dùng ngay phần mở rộng này.

**Chuyển đổi (migrate):** Nâng cấp consumer để sử dụng hợp đồng mới. Trong giai đoạn này, kiểm thử P2/C1 và P1/C2 nếu hai tổ hợp có thể xuất hiện trong triển khai hoặc rollback.

**Thu hẹp (contract):** Chỉ xóa API cũ hoặc ngừng gửi dữ liệu cũ sau khi đã xác nhận không còn consumer được hỗ trợ phụ thuộc vào chúng. Việc xóa cần tuân theo chính sách deprecation và lịch ngừng hỗ trợ đã công bố.

Khi kiểm thử, nên kết hợp kiểm tra source compatibility, binary compatibility, contract test, integration test và kiểm tra hành vi. Với thư viện Java, có thể chạy ứng dụng đã biên dịch từ phiên bản trước trên dependency mới để phát hiện lỗi liên kết. Với REST API, nên lưu các request/response mẫu của consumer đang tồn tại và chạy chúng với provider mới. Với dữ liệu lưu trữ, nên thử đọc dữ liệu được tạo từ các phiên bản trước và thử rollback theo kịch bản đã định.

## 9. Những nhận định dễ gây nhầm lẫn

**“Thêm một phương thức là luôn tương thích.”** Thêm phương thức vào class thường ít rủi ro với caller cũ, nhưng thêm phương thức abstract vào interface có thể ảnh hưởng các lớp triển khai. Thêm overload cũng có thể làm mã nguồn cũ trở nên mơ hồ khi biên dịch lại.

**“Có `@Deprecated` nghĩa là đã an toàn để xóa.”** Annotation chỉ báo trạng thái API. Nó không chứng minh consumer đã chuyển đổi. Cần có thời gian chuyển tiếp và dữ liệu sử dụng thực tế trước khi loại bỏ.

**“Biên dịch được là tương thích.”** Biên dịch kiểm tra một phần source compatibility. Binary cũ có thể lỗi khi liên kết; chương trình vẫn chạy có thể trả kết quả sai do thay đổi hành vi.

**“Thêm trường JSON không thể làm hỏng client.”** Client dùng schema nghiêm ngặt, parser từ chối trường lạ hoặc logic phụ thuộc cấu trúc cố định có thể bị ảnh hưởng. Cần biết cách consumer thực tế đọc dữ liệu.

**“Semantic Versioning tự đảm bảo tương thích.”** Quy tắc phiên bản giúp truyền đạt mức độ thay đổi, nhưng chỉ hữu ích khi nhà cung cấp phân loại đúng thay đổi và kiểm thử hợp đồng. Số phiên bản không thay thế bằng chứng kỹ thuật.

**“Provider mới và consumer mới luôn được triển khai cùng nhau.”** Thực tế có thể có nhiều môi trường, nhiều nhóm phát hành, ứng dụng mobile chưa cập nhật hoặc dữ liệu được lưu qua nhiều năm. Ma trận tương thích cần dựa trên vòng đời triển khai thật.

## 10. Ghi nhớ khi đánh giá một thay đổi

Khi review một thay đổi API hoặc lập kế hoạch nâng cấp, hãy trả lời lần lượt:

- Ai là provider, ai là consumer và hợp đồng nào đang được sử dụng?
- Những cặp phiên bản nào có thể cùng tồn tại: P2/C1, P1/C2 hay cả hai?
- Thay đổi ảnh hưởng source, binary, hành vi, dữ liệu/giao thức hay nền tảng chạy?
- Consumer cũ có tiếp tục hoạt động với provider mới không?
- Consumer mới có phương án làm việc với provider cũ không?
- Trường hợp không hỗ trợ được sẽ được phát hiện và báo lỗi như thế nào?
- Có kiểm thử bằng phiên bản thực tế, dữ liệu cũ và kịch bản rollback không?

Điểm cốt lõi là luôn gắn thuật ngữ tương thích với **phía đang xét và cặp phiên bản cụ thể**. P2/C1 là tương thích ngược từ góc nhìn provider nhưng là tương thích xuôi từ góc nhìn consumer. P1/C2 thì ngược lại. Khi phân biệt được hai góc nhìn này và kiểm tra đúng lớp tương thích, việc nâng cấp thư viện, JDK hoặc dịch vụ Java sẽ có cơ sở rõ ràng hơn và giảm nguy cơ làm gián đoạn những thành phần vẫn đang phụ thuộc vào hợp đồng cũ.
