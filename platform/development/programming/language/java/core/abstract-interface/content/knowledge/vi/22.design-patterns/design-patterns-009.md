# Chọn mẫu theo vấn đề và tránh áp dụng hình thức

Design pattern (mẫu thiết kế) là cách tổ chức các lớp và đối tượng đã được dùng để giải quyết một nhóm vấn đề thiết kế lặp lại. Mẫu giúp diễn đạt một giải pháp bằng ngôn ngữ chung, nhưng **mẫu thiết kế không phải mục tiêu của thiết kế**. Một hệ thống có nhiều pattern chưa chắc tốt hơn; nếu yêu cầu đơn giản, thêm interface, factory hoặc nhiều lớp trung gian có thể khiến mã khó hiểu hơn.

Cách chọn đúng là bắt đầu từ vấn đề đang xảy ra, xác định điều gì có khả năng thay đổi, rồi xem mẫu nào giảm được sự phụ thuộc đó với chi phí hợp lý. Nếu một vài câu lệnh đơn giản đã diễn đạt rõ ý định và chưa có nhu cầu biến thể, giữ cách viết đơn giản là một quyết định thiết kế hợp lệ.

## 1. Bắt đầu từ vấn đề, không bắt đầu từ tên mẫu

Trước khi áp dụng một pattern, hãy trả lời lần lượt các câu hỏi sau:

1. **Mã đang khó ở đâu?** Ví dụ: một thuật toán thay đổi theo loại khách hàng; nhiều nơi phải khởi tạo cùng một nhóm đối tượng; một lớp cần thông báo cho nhiều bên; hoặc hai API không tương thích.
2. **Điều gì thực sự thay đổi?** Phân biệt quy tắc nghiệp vụ hay thay đổi với phần còn lại ổn định. Nếu chỉ có một quy tắc cố định và không có dấu hiệu cần mở rộng, abstraction có thể chưa đem lại lợi ích.
3. **Sự thay đổi đang gây ra chi phí nào?** Chẳng hạn một nhánh `if/else` bị lặp ở nhiều nơi, một thay đổi phải sửa nhiều lớp, hoặc kiểm thử một quy tắc buộc phải khởi tạo cả hệ thống.
4. **Mẫu có cô lập đúng điểm thay đổi không?** Pattern phù hợp phải làm cho mã dễ đọc, dễ kiểm thử hoặc dễ mở rộng hơn ngay trong bối cảnh hiện tại.
5. **Chi phí mới là gì?** Tính cả số lớp và interface tăng thêm, luồng gọi khó lần theo, vòng đời đối tượng, thứ tự sự kiện và yêu cầu bảo trì của nhóm.
6. **Có thể giải quyết bằng cách nhỏ hơn không?** Một hàm riêng, một điều kiện rõ ràng hoặc một object composition đơn giản thường đủ. Không cần tạo cấu trúc pattern chỉ để mã trông giống ví dụ trong sách.

Có thể dùng quy trình ngắn: mô tả vấn đề bằng một câu → xác định trục thay đổi → đưa ra phương án đơn giản nhất → so sánh với một hoặc hai pattern có liên quan → kiểm tra bằng ví dụ và test → chỉ giữ pattern nếu nó giải quyết được chi phí đã xác định.

## 2. Bản đồ vấn đề và mẫu thiết kế

Bảng sau là điểm bắt đầu để lựa chọn, không phải danh sách quy tắc bắt buộc. Một vấn đề có thể có nhiều phương án hợp lệ; hãy chọn phương án khớp với nguyên nhân cụ thể.

| Vấn đề đang gặp | Mẫu đáng cân nhắc | Dấu hiệu mẫu có ích | Khi không nên dùng |
|---|---|---|---|
| Một công việc có nhiều thuật toán thay thế được | **Strategy** | Các cách tính hoặc xử lý khác nhau độc lập với luồng chính và cần chọn theo ngữ cảnh | Chỉ có một thuật toán ổn định, hoặc vài dòng điều kiện dễ đọc hơn |
| Khởi tạo đối tượng phức tạp, nhiều biến thể hoặc cần che giấu quy tắc chọn lớp cụ thể | **Factory Method / Abstract Factory** | Logic tạo đối tượng đang rải rác hoặc nhóm sản phẩm cần tương thích với nhau | Một lời gọi `new` đơn giản đã rõ ràng; factory chỉ chuyển tiếp không thêm quyết định nào |
| Một đối tượng cần thông báo thay đổi cho nhiều bên đăng ký | **Observer** | Bên phát sự kiện không nên biết danh sách cụ thể các bên nhận | Chỉ có một bên nhận cố định; vòng đời đăng ký và hủy đăng ký sẽ tạo thêm rủi ro không cần thiết |
| API có sẵn không khớp giao diện mà mã hiện tại cần | **Adapter** | Cần chuyển đổi một hợp đồng hiện hữu mà không sửa được hoặc không nên sửa mã nguồn bên ngoài | Có thể sửa trực tiếp interface của chính mình mà không ảnh hưởng hợp đồng công khai |
| Muốn thêm trách nhiệm có thể kết hợp theo nhu cầu | **Decorator** | Có nhiều phần bổ sung độc lập cần xếp chồng, ví dụ nén và mã hóa một stream | Chỉ có một lựa chọn đơn giản; chuỗi decorator làm luồng xử lý khó hiểu |
| Hành vi phụ thuộc vào trạng thái hiện tại và quy tắc chuyển trạng thái | **State** | Điều kiện theo trạng thái đã phức tạp, lặp lại và cần quản lý chuyển trạng thái rõ ràng | Chỉ có hai trạng thái với logic nhỏ, ổn định và một điều kiện vẫn dễ đọc |
| Quy trình tổng thể cố định nhưng một số bước có thể thay đổi | **Template Method** | Các lớp chia sẻ cùng khung thuật toán nhưng cần tùy chỉnh một vài bước | Không có quan hệ kế thừa tự nhiên hoặc cần thay đổi từng bước linh hoạt lúc chạy; khi đó composition có thể phù hợp hơn |
| Đối tượng có nhiều tham số tùy chọn hoặc quy tắc xây dựng cần xác minh | **Builder** | Constructor dài, nhiều overload, hoặc trạng thái cấu hình cần rõ ràng | Đối tượng có một vài tham số bắt buộc và có thể tạo an toàn bằng constructor |
| Client phải phối hợp nhiều API/subsystem để thực hiện một tác vụ | **Facade** | Một điểm vào đơn giản giúp giảm sự phụ thuộc trực tiếp vào nhiều thành phần | Lớp facade chỉ chuyển tiếp mọi lời gọi mà không làm rõ hoặc đơn giản hóa cách dùng |

### Những mẫu gần nhau nhưng giải quyết việc khác nhau

- **Strategy và State:** Strategy thay một cách thực hiện theo lựa chọn của client hoặc cấu hình; State biểu diễn hành vi thay đổi theo trạng thái nội tại của đối tượng và thường gắn với chuyển trạng thái.
- **Factory và Builder:** Factory tập trung vào việc chọn hoặc tạo loại đối tượng nào; Builder tập trung vào quá trình lắp ráp một đối tượng có nhiều bước hoặc nhiều tùy chọn.
- **Adapter và Facade:** Adapter làm cho một interface không tương thích có thể được dùng như interface mong muốn; Facade đưa ra một điểm vào đơn giản cho một nhóm API.
- **Decorator và kế thừa:** Decorator thêm trách nhiệm bằng cách bọc một đối tượng, cho phép kết hợp lúc chạy; kế thừa định nghĩa quan hệ kiểu và thường cố định cấu trúc hơn.
- **Observer và gọi hàm trực tiếp:** Observer hữu ích khi có nhiều subscriber độc lập hoặc publisher không nên biết người nhận. Nếu chỉ gọi một collaborator đã biết, lời gọi trực tiếp có thể rõ ràng hơn.

Đừng chọn mẫu chỉ vì tên vấn đề có vẻ giống nhau. Kiểm tra trách nhiệm, chiều phụ thuộc, cách chọn hành vi và vòng đời đối tượng trong tình huống cụ thể.

## 3. Ví dụ Java: khi giải pháp đơn giản là lựa chọn đúng

Giả sử một ứng dụng nhỏ có đúng hai hình thức giao hàng: tiêu chuẩn và nhanh. Phí cơ bản lần lượt là 20.000 và 40.000 đồng; mỗi 500 g vượt quá 1 kg cộng thêm 5.000 đồng. Yêu cầu hiện tại không có hãng vận chuyển bên ngoài, không thay đổi thuật toán bằng cấu hình và không có nhiều nơi phải tự chọn chính sách. Một phương thức với kiểu enum và biểu thức switch đủ rõ ràng để mô tả quy tắc.

Lưu toàn bộ chương trình sau vào tệp **PatternChoiceDemo.java**:

~~~java
import java.util.Objects;

public class PatternChoiceDemo {
    enum Delivery {
        STANDARD, EXPRESS
    }

    static long shippingFee(Delivery delivery, int weightGrams) {
        Objects.requireNonNull(delivery, "delivery");
        if (weightGrams < 0) {
            throw new IllegalArgumentException("weight must not be negative");
        }

        long baseFee = switch (delivery) {
            case STANDARD -> 20_000L;
            case EXPRESS -> 40_000L;
        };
        long extraGrams = Math.max(0L, (long) weightGrams - 1_000L);
        long extraBlocks = (extraGrams + 499L) / 500L;
        return baseFee + extraBlocks * 5_000L;
    }

    public static void main(String[] args) {
        System.out.println("standard=" + shippingFee(Delivery.STANDARD, 1_500));
        System.out.println("express=" + shippingFee(Delivery.EXPRESS, 1_500));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac PatternChoiceDemo.java
java PatternChoiceDemo
~~~

Kết quả stdout:

~~~text
standard=25000
express=45000
~~~

Ví dụ cố ý **không** tạo interface Strategy, factory hay lớp con: chỉ có một trục lựa chọn nhỏ, hai giá trị xác định và một quy tắc cộng trọng lượng dùng chung. Enum ngăn lỗi gõ sai tên hình thức vận chuyển; switch expression buộc xử lý đủ các giá trị hiện có. Kiểm tra trọng lượng âm ngăn một đầu vào sai làm ra mức phí không có ý nghĩa. Trường hợp 1.500 g có đúng một khối 500 g vượt ngưỡng nên tăng 5.000 đồng.

### Khi yêu cầu thay đổi, mẫu nào mới có giá trị?

| Yêu cầu mới | Phương án có thể phù hợp | Cần cân nhắc |
|---|---|---|
| Hàng chục chính sách tính phí độc lập, chọn theo cấu hình và kiểm thử riêng | Strategy qua interface chính sách | Cần nơi chọn chiến lược và hợp đồng tính phí thống nhất |
| Tích hợp API của hãng vận chuyển trả giá ở đơn vị hoặc kiểu dữ liệu khác | Adapter chuyển hợp đồng bên ngoài sang hợp đồng ứng dụng | Cần quy định làm tròn, đơn vị và xử lý lỗi |
| Thêm logging, đo thời gian hoặc audit một cách tùy chọn quanh lời gọi tính phí | Decorator bọc cùng interface | Thứ tự bọc và cách truyền exception phải rõ |
| Mỗi loại đơn có cùng quy trình kiểm tra → tính phí → lưu kết quả, nhưng vài bước thay đổi | Template Method, nếu quan hệ kế thừa tự nhiên | Giữ bước bắt buộc và bất biến ở lớp cha |
| Tạo nhiều đối tượng vận chuyển cụ thể trong một workflow ổn định | Factory Method | Chỉ có lợi nếu điểm tạo sản phẩm thực sự cần đa hình |
| Nhiều thành phần cần đăng ký khi đơn hàng đã giao | Listener hoặc Observer | Quản lý đăng ký, thứ tự và lỗi listener |

Đây là những phương án cho **những vấn đề mới khác nhau**, không phải một danh sách lớp cần thêm cùng lúc. Nếu ứng dụng chỉ có hai mức phí đơn giản, tiếp tục dùng phiên bản switch ở trên là lựa chọn có căn cứ. Khi một thay đổi thực tế tạo ra nhiều nhánh hoặc sự phụ thuộc gây tốn công bảo trì, lúc đó mới refactor phần thay đổi thích hợp.


## 4. Nhận diện việc áp dụng pattern theo hình thức

Một số dấu hiệu cho thấy cấu trúc đã phức tạp hơn vấn đề cần giải quyết:

- **Tên pattern xuất hiện nhưng lý do không rõ:** nhóm có thể giải thích lớp nào chịu trách nhiệm gì, nhưng không chỉ ra được chi phí nào được giảm.
- **Abstraction chỉ chuyển tiếp:** interface có một implementation, không có điểm thay đổi hoặc ràng buộc hữu ích, và mỗi lớp chỉ gọi sang lớp kế tiếp.
- **Factory cho mọi lần `new`:** nếu factory không che giấu lựa chọn, không kiểm soát vòng đời và không bảo vệ quy tắc xây dựng, nó có thể chỉ tạo thêm một bước điều hướng.
- **Strategy cho một biểu thức nhỏ:** một điều kiện đơn giản dễ hiểu bị tách thành nhiều class dù không có nhu cầu thay thế thuật toán.
- **Singleton dùng để chia sẻ mọi thứ:** tính duy nhất toàn cục tạo phụ thuộc ẩn và làm test dễ bị ảnh hưởng bởi trạng thái còn sót lại. Chỉ dùng khi tính duy nhất thực sự là yêu cầu miền hoặc vòng đời.
- **Observer làm luồng điều khiển khó đoán:** nhiều listener gọi lẫn nhau, lỗi ở một listener ảnh hưởng các bên khác, hoặc không biết khi nào đăng ký/hủy đăng ký. Cần định nghĩa rõ vòng đời, thứ tự và cách xử lý lỗi.
- **Mẫu được lồng quá nhiều:** người đọc phải đi qua nhiều interface, factory và wrapper mới tìm được hành vi thực tế. Hãy kiểm tra xem mỗi lớp có trách nhiệm và lợi ích độc lập hay không.

Lưu ý: một dấu hiệu riêng lẻ chưa đủ kết luận rằng pattern sai. Ví dụ, một Strategy có một implementation hiện tại vẫn có thể hợp lý nếu đó là ranh giới quan trọng với API bên ngoài hoặc cần thay đổi cấu hình lúc chạy. Hãy xem toàn bộ ngữ cảnh và chi phí bảo trì.

## 5. Chọn giữa các phương án một cách có căn cứ

Khi có nhiều lựa chọn, đánh giá chúng theo cùng một số tiêu chí:

1. **Độ rõ ràng:** người mới có hiểu ý định và tìm được nơi xử lý nghiệp vụ chính không?
2. **Khả năng thay đổi:** một biến thể mới cần sửa bao nhiêu vị trí? Phần ổn định có phải biết chi tiết của phần thay đổi không?
3. **Khả năng kiểm thử:** có thể kiểm tra quy tắc độc lập hay phải khởi tạo quá nhiều thành phần?
4. **Độ an toàn:** pattern có giúp giữ invariant, quản lý tài nguyên, trạng thái hoặc vòng đời đăng ký tốt hơn không?
5. **Chi phí đọc và bảo trì:** số lượng lớp, indirection và các quy ước mới có đáng với lợi ích hiện tại không?
6. **Khả năng quay lại:** có thể bắt đầu đơn giản và refactor sau khi xuất hiện nhu cầu thực tế không? Có test nào bảo vệ hành vi trước khi thay cấu trúc không?

Không cần chấm điểm máy móc cho mọi thay đổi. Dùng các tiêu chí này để giải thích trade-off khi thiết kế không hiển nhiên. Nếu hai phương án đáp ứng yêu cầu như nhau, ưu tiên phương án ít khái niệm mới và dễ hiểu hơn với nhóm.

## 6. Quy trình refactor an toàn

Khi một đoạn mã bắt đầu có vấn đề, thực hiện theo từng bước:

1. **Ghi lại hành vi hiện tại.** Tạo hoặc cập nhật test cho các trường hợp quan trọng trước khi thay cấu trúc.
2. **Chỉ ra trục thay đổi.** Ví dụ: quy tắc tính giá, nguồn dữ liệu, loại thông báo hoặc quy trình tạo đối tượng.
3. **Giữ nguyên phần ổn định.** Tách đúng phần thay đổi khỏi luồng chính, thay vì chuyển toàn bộ hệ thống sang cấu trúc mới.
4. **Áp dụng mẫu nhỏ nhất có ích.** Bắt đầu bằng một abstraction có hợp đồng rõ ràng; chỉ thêm Factory, Builder hoặc các lớp phụ khi chúng xử lý một trách nhiệm thực sự.
5. **So sánh trước và sau.** Kiểm tra output và test; xác nhận mã gọi dễ hiểu hơn, thay đổi mới ít lan rộng hơn hoặc việc kiểm thử đơn giản hơn.
6. **Xóa cấu trúc thừa.** Nếu abstraction không còn giúp giảm phụ thuộc hoặc làm rõ trách nhiệm, cân nhắc bỏ nó trong một refactor riêng có test.

## 7. Bài tập tự đánh giá

Với mỗi tình huống, hãy nói rõ vấn đề trước khi chọn pattern:

- **A.** Một chương trình có duy nhất một công thức phí vận chuyển, không có cấu hình hay biến thể. Có nên tạo Strategy ngay không? Giải thích chi phí của interface mới.
- **B.** Có nhiều cách tính phí theo vùng giao hàng; quy tắc thay đổi độc lập và cần được kiểm thử riêng. Strategy có giúp không? Phần nào nên phụ thuộc vào interface?
- **C.** Một SDK bên ngoài cung cấp `LegacyPaymentClient`, nhưng ứng dụng cần interface `PaymentGateway` và không thể sửa SDK. Vì sao Adapter phù hợp hơn Facade trong trường hợp này?
- **D.** Một đơn hàng được gửi đến nhiều subscriber độc lập khi trạng thái thay đổi. Những gì cần quyết định về đăng ký, hủy đăng ký, lỗi listener và thứ tự thông báo trước khi dùng Observer?
- **E.** Một constructor chỉ có hai tham số bắt buộc. Builder có làm cách tạo đối tượng rõ hơn không, hay chỉ thêm mã phải duy trì?

Một câu trả lời tốt không chỉ nêu tên pattern. Nó mô tả vấn đề, chỉ ra trách nhiệm nào cần tách, giải thích tại sao mẫu phù hợp và nêu được chi phí hoặc tình huống khiến mẫu không còn cần thiết.

## 8. Nguyên tắc ghi nhớ

Mẫu thiết kế là công cụ để quản lý sự thay đổi và làm rõ trách nhiệm. Chọn pattern sau khi xác định được vấn đề, trục thay đổi và giới hạn của phương án đơn giản nhất. Dùng một mẫu khi nó giúp hệ thống dễ đọc, kiểm thử hoặc mở rộng hơn trong tình huống hiện tại; tránh thêm cấu trúc chỉ để tuân theo hình thức.
