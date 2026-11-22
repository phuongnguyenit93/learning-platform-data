# Kết hợp sealed type với exhaustive switch

**Chủ đề:** Java Core Pattern Matching — Kết hợp patterns. Nội dung sử dụng Java 21 trở lên, khi pattern matching for switch (JEP 441) và record patterns (JEP 440) đã là tính năng chính thức; không cần `--enable-preview`.

## 1. Bài toán: xử lý đầy đủ các dạng giá trị

Một biến kiểu cha có thể đại diện cho nhiều kiểu con. Ví dụ, hệ thống xử lý thông điệp có hai dạng: **Ping** không mang dữ liệu và **Submit** mang nội dung cùng độ ưu tiên. Khi xử lý thông điệp, ta muốn bảo đảm **mọi dạng hợp lệ đều có nhánh xử lý**. Nếu chương trình bổ sung kiểu thông điệp mới, tốt nhất trình biên dịch phải nhắc ta cập nhật mã phân nhánh.

Một hệ phân loại dùng kiểu cha mở rộng tự do thường viết theo hướng kiểm tra nhiều `instanceof` rồi kết thúc bằng nhánh dự phòng. Với hệ thống chỉ cho phép một tập hợp kiểu con được xác định, Java cung cấp **sealed class/interface**. Ghép nó với **switch expression** hỗ trợ type pattern, ta nhận được phép kiểm tra **exhaustiveness** ngay lúc biên dịch: trình biên dịch có thể xác định liệu các nhánh switch đã xử lý đủ các khả năng kiểu được phép hay chưa.

Ý nghĩa của ba thành phần:

- **Sealed type:** khai báo những kiểu nào được phép trực tiếp kế thừa/triển khai kiểu cha.
- **Pattern:** mô tả kiểu và, nếu cần, trích xuất các thành phần của record trong mỗi nhánh.
- **Exhaustive switch:** có nhánh áp dụng cho mọi giá trị thuộc các kiểu khả dĩ của selector, theo phân tích tĩnh của Java. Với switch expression, tính đầy đủ là yêu cầu biên dịch.

Vì vậy sealed type cung cấp thông tin về miền kiểu, pattern diễn tả từng trường hợp, còn switch tận dụng thông tin đó để kiểm tra tính bao phủ.

## 2. Khai báo một miền kiểu đóng bằng sealed interface

~~~java
sealed interface Message permits Ping, Submit {}

record Ping() implements Message {}

record Submit(String text, int priority) implements Message {}
~~~

Đoạn trên minh họa một nhóm khai báo trong cùng phạm vi được phép. **Message** chỉ cho phép hai kiểu con trực tiếp **Ping** và **Submit**. Record vốn là final, nên hai record này đáp ứng yêu cầu đối với một kiểu triển khai trực tiếp sealed interface.

Một kiểu con trực tiếp của sealed class/interface phải thể hiện rõ một trong các hình thức: **final**, **sealed** hoặc **non-sealed** (record ngầm final). Quy tắc về vị trí cũng quan trọng: trong named module, permitted subclasses phải nằm trong cùng module; khi không có named module, chúng phải nằm trong cùng package. Tên trong **permits** phải tương ứng với các kiểu con hợp lệ.

Sealed không đồng nghĩa với “mọi object trong ứng dụng chỉ thuộc đúng hai class đó” trong mọi thiết kế. Nếu một nhánh permitted được khai báo **non-sealed**, các kiểu dẫn xuất dưới nhánh đó có thể tiếp tục mở rộng. Điều Java kiểm soát là **các kiểu con trực tiếp**, còn switch phải bao phủ đúng cấu trúc phân cấp thực tế, chẳng hạn bằng một type pattern cho cả nhánh non-sealed.

## 3. Vì sao có thể bỏ default mà vẫn exhaustive?

Với selector kiểu **Message**, hai record trên là tất cả các kiểu con trực tiếp hợp lệ:

~~~java
static String kind(Message message) {
    return switch (message) {
        case Ping p -> "PING";
        case Submit s -> "SUBMIT";
    };
}
~~~

Đây là một **switch expression** có giá trị trả về. Mặc dù không có **default**, trình biên dịch biết mỗi giá trị Message khác null đều thuộc một trong các nhánh được bao phủ. Nó chấp nhận switch vì miền kiểu được sealed interface đóng lại.

Trong trường hợp này, hai type pattern **Ping p** và **Submit s** đã đủ để chứng minh exhaustiveness; record pattern không phải điều kiện bắt buộc. Ta dùng record pattern khi thật sự muốn nhìn thấy các component, chẳng hạn **Submit(var text, var priority)**.

**Phân biệt exhaustiveness với null:** tính đầy đủ dựa trên kiểu sealed không biến selector null thành một kiểu con của Message. Nếu **message == null** và switch không có nhánh null phù hợp, switch sẽ ném **NullPointerException** khi chạy. Muốn xử lý null có chủ đích, hãy thêm **case null**. Một switch có đủ nhánh kiểu nhưng chưa xử lý null vẫn có thể biên dịch.

### Khi các nhánh có guard

Giả sử chỉ chấp nhận Submit có text không trống và priority từ 1 trở lên:

~~~java
return switch (message) {
    case Ping() -> "pong";
    case Submit(var text, var priority)
            when text != null && !text.isBlank() && priority >= 1 ->
            "accepted";
    case Submit(var text, var priority) -> "rejected";
    case null -> "missing message";
};
~~~

Điểm then chốt: nhánh Submit đầu có **when**, nên nó chỉ bao phủ **một phần** giá trị Submit. Nhánh Submit thứ hai không có guard bao phủ những Submit còn lại. Nếu chỉ giữ nhánh có guard, switch expression có thể không exhaustive, vì Submit không thỏa điều kiện không được xử lý.

Nhánh cụ thể với guard phải đứng trước nhánh rộng cùng kiểu; đặt nhánh Submit tổng quát trước có thể làm nhánh sau bị che khuất và bị từ chối khi biên dịch. Guard chỉ được đánh giá sau khi pattern khớp và các biến đã được ràng buộc.

## 4. Ví dụ Java 21 hoàn chỉnh

Chương trình sau minh họa sealed interface, record pattern, guard, xử lý null và exhaustive switch expression **không có default**. Lưu mã trong tệp **SealedSwitchDemo.java**:

~~~java
public class SealedSwitchDemo {
    sealed interface Message permits Ping, Submit {}

    record Ping() implements Message {}

    record Submit(String text, int priority) implements Message {}

    static String handle(Message message) {
        return switch (message) {
            case Ping() -> "pong";

            case Submit(String text, int priority)
                    when text != null && !text.isBlank() && priority >= 1 ->
                    "accepted: " + text + ", priority=" + priority;

            case Submit(var text, var priority) -> "rejected";

            case null -> "missing message";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(new Ping()));
        System.out.println(handle(new Submit("deploy", 2)));
        System.out.println(handle(new Submit(" ", 2)));
        System.out.println(handle(new Submit(null, 2)));
        System.out.println(handle(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 21+:

~~~bash
javac SealedSwitchDemo.java
java SealedSwitchDemo
~~~

Kết quả chính xác:

~~~text
pong
accepted: deploy, priority=2
rejected
rejected
missing message
~~~

Giải thích từng trường hợp:

1. **new Ping()** khớp **case Ping()**, trả về pong.
2. **Submit("deploy", 2)** khớp record pattern và guard, nên trả về nội dung được chấp nhận.
3. **Submit(" ", 2)** khớp kiểu Submit nhưng không thỏa **text.isBlank() == false**, đi vào nhánh Submit không guard.
4. **Submit(null, 2)** vẫn là một Submit hợp lệ về kiểu record. Guard đầu dùng **text != null** trước khi gọi **isBlank()**, vì vậy không gây NullPointerException và chuyển sang nhánh Submit dự phòng.
5. **null** khớp **case null**. Nhánh này xử lý đầu vào null một cách tường minh.

Trong đoạn mã, **Submit(String text, int priority)** là một record pattern. Nó trích component **text** và **priority** tại vị trí tương ứng trong record, không gọi constructor. Mẫu record với thành phần tham chiếu có thể ràng buộc giá trị null khi mẫu thành phần là unconditional; ví dụ đã kiểm tra null riêng bằng guard. Với một record lồng cụ thể như **Address(...)**, record con null sẽ không khớp mẫu lồng đó.

## 5. Thêm một subtype mới: trình biên dịch giúp phát hiện thiếu nhánh

Giả sử sau này muốn có thêm thông điệp **Cancel**. Ta sửa khai báo của hierarchy:

~~~java
// Minh họa thay đổi một phần của ví dụ trên, không phải chương trình độc lập.
sealed interface Message permits Ping, Submit, Cancel {}

record Cancel(String reason) implements Message {}
~~~

Lúc này phương thức **handle(Message message)** trước đó mới chỉ có nhánh bao phủ Ping và Submit; **Cancel** chưa được xử lý. Vì switch expression **không có default** và không bao phủ hết các kiểu permitted, trình biên dịch báo lỗi kiểu **the switch expression does not cover all possible input values**. Bản thân việc thêm class mà không thêm xử lý phải khiến ta đánh giá lại logic.

Cách cập nhật rõ ràng là thêm một nhánh mới trước case null:

~~~java
case Cancel(var reason) -> "cancelled: " + reason;
~~~

Điều này buộc người phát triển chủ động quyết định ngữ nghĩa của Cancel. Việc dùng **default** quá sớm trong switch của sealed hierarchy có thể làm mất lợi thế trên: khi thêm subtype, code vẫn biên dịch và nhánh mới bị gom vào default, dù nghiệp vụ có thể cần xử lý riêng.

**Khi nào default vẫn phù hợp?** Khi một yêu cầu thực sự quy định cùng một hành vi dự phòng cho mọi kiểu khác, hoặc tại ranh giới cần chiến lược từ chối chung. Nhưng nếu mục đích là “thêm mỗi subtype phải rà soát từng nơi xử lý”, không viết default chỉ để làm trình biên dịch im lặng.

Cũng cần phân biệt biên dịch với thay đổi binary/runtime: nếu các class được biên dịch, triển khai và nâng cấp không đồng bộ, hierarchy thực tế có thể thay đổi sau khi một switch được biên dịch. Java có cơ chế lỗi runtime (ví dụ **MatchException**) nếu một switch được cho là exhaustive gặp giá trị không được bất kỳ nhánh nào xử lý do tình huống tương thích/biên dịch riêng lẻ. Bảo đảm compile-time là rất hữu ích nhưng không thay thế quy trình biên dịch và triển khai nhất quán.

## 6. Sealed hierarchy có nhiều tầng và non-sealed

Ví dụ dưới đây minh họa các nhánh, chỉ để giải thích cấu trúc:

~~~java
sealed interface Event permits Created, UpdateEvent {}

record Created(String id) implements Event {}

non-sealed interface UpdateEvent extends Event {}
~~~

**Event** chỉ có hai kiểu con trực tiếp được phép. Tuy nhiên **UpdateEvent** được khai báo non-sealed, nghĩa là các class triển khai UpdateEvent có thể mở rộng về sau. Để switch bao phủ nhánh này, ta có thể dùng một type pattern tổng quát:

~~~java
static String label(Event event) {
    return switch (event) {
        case Created(var id) -> "created " + id;
        case UpdateEvent u -> "update";
        case null -> "null event";
    };
}
~~~

Nhánh **case UpdateEvent u** bao phủ mọi giá trị thuộc interface UpdateEvent, kể cả các class triển khai được thêm hợp lệ sau này. Nhờ đó switch vẫn exhaustive đối với miền đã công bố. Nếu lại muốn phân biệt từng loại UpdateEvent và buộc compiler nhắc khi bổ sung loại mới, nên cân nhắc giữ nhánh trung gian cũng là sealed, với tập các kiểu con được định nghĩa rõ.

Trong một sealed hierarchy nhiều tầng, có thể liệt kê các kiểu lá trong switch nếu phép phân tích exhaustiveness chứng minh chúng bao phủ đủ các nhánh. Không cần nhất thiết có đúng một case cho mỗi tên xuất hiện trong **permits** ở cấp ngoài; điều cần là **bao phủ mọi giá trị khả dĩ**.

## 7. So sánh với enum, if/else và switch có default

| Cách mô hình hóa | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| **enum + switch** | Hợp với một tập lựa chọn cố định, mỗi lựa chọn đơn giản | Khó biểu diễn mỗi trường hợp có tập component và kiểu dữ liệu riêng như các record con |
| **sealed interface + switch pattern** | Mỗi subtype có dữ liệu và hành vi khác nhau; compiler kiểm tra bao phủ các subtype | Phải quản lý hierarchy và hiểu tính mở rộng của nhánh non-sealed |
| **if/else + instanceof** | Thuận tiện với một vài kiểm tra tuyến tính hoặc kiểu cha mở | Không tự mang cơ chế exhaustiveness giống switch expression trên sealed hierarchy |
| **switch có default** | Cung cấp nhánh dự phòng tường minh cho trường hợp khác | Có thể che việc bổ sung subtype mới mà chưa được thiết kế xử lý |

Không phải mọi lựa chọn hữu hạn đều cần sealed type. Dùng enum khi chỉ có một số trạng thái hoặc mã định danh cố định và dữ liệu đi kèm tương đối đồng nhất. Sealed hierarchy phát huy tác dụng khi mỗi trường hợp là **một kiểu riêng**, chẳng hạn kết quả xử lý gồm Success(data), ValidationError(errors) và RetryAfter(duration), hoặc các nút biểu thức có cấu trúc khác nhau.

## 8. Kết hợp record patterns lồng nhau mà vẫn giữ exhaustiveness

Exhaustiveness theo sealed type là chuyện **bao phủ các subtype**, còn record pattern lồng nhau là chuyện **chọn hình dạng component cụ thể**. Hai khía cạnh hỗ trợ nhau nhưng không thay thế nhau.

Giả sử Submit có component là một record khác:

~~~java
record Payload(String kind, int size) {}

record Submit(Payload payload, int priority) implements Message {}
~~~

Đây là một **phiên bản thiết kế thay thế** cho record Submit trong ví dụ chính, không dùng đồng thời hai khai báo trùng tên. Nếu ta viết case chỉ nhận Submit có payload khác null:

~~~java
case Submit(Payload(var kind, int size), int priority) ->
        "payload " + kind;
~~~

thì một giá trị **Submit(null, 1)** không khớp case đó. Dù subtype Submit đã được nhắc tên, switch vẫn cần một nhánh xử lý những Submit khác, chẳng hạn:

~~~java
case Submit(var payload, var priority) -> "invalid submit";
~~~

Bài học là **một case nhắc đến subtype không nhất thiết bao phủ toàn bộ subtype**, nhất là khi mẫu con yêu cầu record lồng, có guard, hoặc ràng buộc khác. Muốn khẳng định exhaustive, hãy đánh giá phạm vi thực sự được mỗi mẫu bao phủ.

## 9. Những lỗi thường gặp và cách sửa

1. **Chỉ có các case có when:** Mọi Submit đều có thể không thỏa guard. Hãy thêm case không guard (hoặc một nhánh khác thực sự bao phủ phần còn lại).
2. **Nhầm “có case của subtype” với “bao phủ cả subtype”:** Record pattern lồng yêu cầu component con phù hợp. Phải tính cả null và các dạng dữ liệu không khớp.
3. **Đặt case rộng trước case hẹp:** Case không guard cho Submit có thể chiếm hết mọi trường hợp của Submit và khiến case cụ thể sau bị dominated.
4. **Thêm default trong mọi switch:** Có thể làm mất cảnh báo khi thêm kiểu permitted mới. Chỉ dùng khi nghiệp vụ thật sự cần hành vi chung.
5. **Quên null:** Sealed interface mô tả các subtype hợp lệ, không khiến selector null tự động trở thành Ping/Submit. Hãy dùng case null nếu cần xử lý, hoặc chấp nhận NullPointerException theo hợp đồng của phương thức.
6. **Tưởng sealed đóng mọi tầng:** Một permitted subtype **non-sealed** vẫn cho phép các descendant mới. Hãy dùng type pattern bao trùm nhánh đó khi cần exhaustive.
7. **Lạm dụng pattern để thay validation:** Kiểm tra kiểu và trích component không tự bảo đảm trường dữ liệu không rỗng, số dương, hay điều kiện nghiệp vụ khác.
8. **Sai phạm vi biến:** Biến được giới thiệu bởi pattern/record pattern chỉ dùng được nơi matching thành công và theo quy tắc scope của Java.
9. **Thay đổi hierarchy mà chỉ biên dịch một phần:** Cần biên dịch, kiểm thử và triển khai các thành phần liên quan cùng nhau để tránh lỗi runtime bất ngờ.

## 10. Checklist thiết kế và kiểm thử

Trước khi chốt một switch trên sealed hierarchy, kiểm tra rằng:

- Kiểu selector thực sự là sealed (hoặc một miền được phân tích đầy đủ) và các subtype được khai báo đúng.
- Mọi **permitted subtype** có ít nhất một tập case bao phủ toàn bộ các giá trị cần xử lý; chú ý guard và mẫu record lồng.
- Các nhánh cụ thể đứng trước nhánh rộng; mỗi nhánh có ý nghĩa nghiệp vụ rõ.
- Quyết định rõ với **null**: xử lý bằng case null hay để lỗi theo hợp đồng.
- Khi thêm một subtype mới, thử biên dịch để xác nhận những switch cần rà soát được phát hiện.
- Có kiểm thử cho các subtype, các trường hợp biên của guard và component con null (nếu mô hình cho phép).
- Nếu hierarchy cho phép một nhánh **non-sealed**, hiểu rằng descendants dưới nhánh đó còn có thể mở rộng.

**Điểm cốt lõi:** sealed type tạo ra một miền kiểu mà compiler có thể phân tích, còn pattern matching for switch biến từng subtype thành một nhánh xử lý có ý nghĩa. Kết hợp đúng cho phép **switch expression không cần default mà vẫn exhaustive**, đồng thời đưa lỗi thiếu nhánh khi bổ sung subtype mới lên giai đoạn biên dịch.