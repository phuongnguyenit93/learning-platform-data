# Không dùng reflection chỉ để tránh thiết kế API rõ ràng

## 1. Vấn đề thực sự: có thể gọi động không có nghĩa là nên gọi động

Trong Java, Reflection cho phép chương trình đọc thông tin về class, constructor, field, method và thực hiện một số thao tác lúc runtime. Ví dụ:

```java
Method method = target.getClass().getMethod(
        methodName, String.class, String.class);
method.invoke(target, recipient, message);
```

Đoạn mã này là **mảnh minh họa**, giả định đã có `target`, `methodName`, `recipient`, `message` và import `java.lang.reflect.Method`; caller phải xử lý ngoại lệ Reflection. Nó có thể hữu ích khi method thực sự chỉ được xác định vào runtime. Nhưng nếu hệ thống vốn biết trước hai nghiệp vụ `sendEmail(...)` và `sendPush(...)`, việc nhận chuỗi tên method để chọn một trong hai thường là dấu hiệu **chưa định nghĩa hợp đồng API rõ ràng**.

Reflection là **cơ chế kỹ thuật để thao tác với thành viên đã được mô tả bằng metadata**. Nó không thay thế những quyết định thiết kế:

- Người gọi được phép thực hiện hành động nào?
- Mỗi hành động nhận tham số gì, trả kết quả gì, ném lỗi gì?
- Thành phần nào chịu trách nhiệm kiểm tra dữ liệu và quy tắc nghiệp vụ?
- Chọn triển khai bằng cách nào, tại thời điểm biên dịch hay runtime?
- Khi đổi tên method hoặc thay đổi chữ ký, ai cần biết và hệ thống được kiểm tra ra sao?

Nếu câu trả lời là “ghép chuỗi tên method rồi thử invoke”, các thông tin hợp đồng ấy đang bị đẩy từ mã nguồn và compiler sang runtime.

**Nguyên tắc:** Khi các loại thao tác và đối tượng tương tác đã biết lúc phát triển, hãy ưu tiên API có tên, kiểu dữ liệu và trách nhiệm cụ thể. Dùng Reflection khi nhu cầu thật sự là khám phá/ghép nối thành viên động và đã xác định rõ ranh giới của tính động ấy.

## 2. Vì sao reflection có thể làm API khó hiểu hơn?

### a) Mất kiểm tra kiểu ngay tại nơi gọi

Ví dụ gọi trực tiếp:

```java
notificationService.send(Channel.EMAIL, "lan@example.com", "Hello");
```

Compiler biết tên method `send`, kiểu `Channel`, hai tham số `String` và kiểu trả về. Nếu đổi chữ ký hoặc gọi sai kiểu, nhiều lỗi sẽ xuất hiện ngay khi biên dịch.

Với một hệ thống tự ghép lời gọi:

```java
dispatcher.invoke("sendEmail", "lan@example.com", "Hello");
```

Compiler chỉ thấy `invoke(String, Object...)` hay một chữ ký chung tương tự, không tự kiểm tra sự tồn tại của nghiệp vụ `sendEmail` trên đích thật. Lỗi tên và overload có thể chỉ lộ ra khi đường chạy ấy thực sự được thực hiện.

**Lưu ý:** Reflection API vẫn có kiểm tra runtime; không phải “không kiểm tra kiểu”. Điểm khác biệt là phần lớn sai sót về tên/signature bị phát hiện **muộn hơn** và trở thành trách nhiệm của người viết dispatcher/framework.

### b) Hợp đồng bị thay bằng chuỗi và quy ước ngầm

Một chuỗi như `"sendEmail"` không tự nói lên tham số, kiểu kết quả, quyền gọi, validation hay ý nghĩa nghiệp vụ. Nếu ứng dụng quyết định tên method từ request của client, còn có nguy cơ tạo tập hành động truy cập rộng hơn dự kiến.

Một API tốt thể hiện lựa chọn trong kiểu dữ liệu, chẳng hạn `enum Channel { EMAIL, PUSH }`, và gom quá trình dispatch trong một service có trách nhiệm cụ thể.

### c) Khó bảo trì khi refactor

IDE và compiler có thể hỗ trợ đổi tên method trực tiếp, tìm caller hoặc kiểm tra thay đổi signature. Tên method nằm trong chuỗi runtime có thể không được cập nhật hoặc kiểm tra theo cùng mức độ. Unit test chỉ bao phủ được các nhánh đã chạy; các nhánh reflective bị bỏ sót vẫn có nguy cơ lỗi.

### d) Sai loại thành viên, quyền và classloader

Các API như `getMethod` và `getDeclaredMethod` không giống nhau. `getMethod` tra cứu public method theo quy tắc của nó; `getDeclaredMethod` tìm method khai báo trực tiếp trong class, kể cả non-public, nhưng việc **tìm thấy** không bảo đảm **gọi được**. Overload yêu cầu danh sách kiểu tham số chính xác; primitive `int.class` khác `Integer.class`. Java module, visibility, receiver và classloader còn bổ sung các điều kiện truy cập.

Nếu chọn Reflection chỉ để gọi hai thao tác đã biết, ứng dụng tự nhận thêm nhiều chi phí chẩn đoán này mà không có lợi ích tương xứng.

### e) Khó phân định ngoại lệ và lỗi nghiệp vụ

`Method.invoke(...)` có thể ném `NoSuchMethodException` ở bước tìm (qua `getMethod`), `IllegalAccessException`, `IllegalArgumentException` hoặc `InvocationTargetException` khi gọi. Nếu method đích ném exception, `InvocationTargetException` bọc lỗi gốc và phải phân tích `getCause()`. API kiểu tường minh thường biểu diễn lỗi nghiệp vụ gần với nơi phát sinh hơn và giữ stack trace đơn giản hơn.

Đừng vội gộp mọi trường hợp thành `catch (Exception) { return null; }`: làm vậy che khuất cấu hình sai, lỗi lập trình và lỗi domain.

## 3. Phản ví dụ: dispatcher gọi method theo tên

Giả sử hệ thống gửi thông báo có hai kênh cố định. Một thiết kế dễ mắc lỗi là truyền tên method tới helper dùng Reflection:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

class StringMethodDispatcher {
    static void dispatch(
            Object target,
            String methodName,
            String recipient,
            String message)
            throws NoSuchMethodException,
                   IllegalAccessException,
                   InvocationTargetException {
        Method method = target.getClass().getMethod(
                methodName, String.class, String.class);
        method.invoke(target, recipient, message);
    }
}
```

Đây là một class **biên dịch được như thành phần thư viện**, không có `main` nên không phải chương trình chạy độc lập. Để thành công, class đích phải cung cấp public method phù hợp và các điều kiện truy cập runtime phải cho phép gọi.

Một lời gọi kiểu này thường tồn tại trong ứng dụng:

```java
StringMethodDispatcher.dispatch(
        someService, "sendEmail", "lan@example.com", "Hello");
```

Đoạn gọi là minh họa trong method đã có biến `someService`. Cả tên `"sendEmail"` và kiểu `Object` không giúp compiler ràng buộc API gửi thông báo cụ thể. Đổi tên method đích nhưng quên chuỗi khiến `NoSuchMethodException` xảy ra lúc chạy.

Những câu hỏi cần đặt ra trước khi xây dispatcher:

1. Tập hành động có thật sự thay đổi runtime, hay chỉ có hai hoặc ba nhánh đã biết?
2. Vì sao caller được cấp quyền chọn **tên member Java**, thay vì chọn một hành động nghiệp vụ đã công bố?
3. Nếu thêm action mới, có thể cập nhật một interface/enum/registry được kiểm soát không?
4. Khi một action không hợp lệ, muốn lỗi ở compile time, validation time hay tới khi Reflection lookup?
5. Có cần tách quyền truy cập member của Java khỏi quyền thực hiện nghiệp vụ của client không?

Trong trường hợp này, ưu tiên thiết kế API kiểu tường minh sẽ dễ kiểm tra hơn.

## 4. Thiết kế lại: một contract, nhiều implementation

Giả sử Email và Push đều thực hiện cùng một thao tác nghiệp vụ là “gửi thông báo”. Ta có thể biểu diễn điều ấy bằng `interface Sender`, dùng `enum Channel` làm tập lựa chọn công khai và `NotificationService` để phối hợp.

| Thành phần | Trách nhiệm | Lợi ích thiết kế |
| --- | --- | --- |
| `Sender` | Khai báo `send(recipient, body)` | Chữ ký và ý nghĩa chung rõ ràng |
| `EmailSender` / `PushSender` | Thực hiện hành vi cho từng kênh | Thay thế/mock/test độc lập |
| `Channel` | Xác định các lựa chọn hợp lệ | Caller không biết tên method nội bộ |
| `NotificationService` | Chọn sender rồi gọi interface | Kiểm soát điều phối và lỗi unsupported ở một nơi |
| `Map<Channel, Sender>` | Registry của các implementation đã được chọn | Mở rộng nhánh cụ thể mà không tạo dispatcher Reflection |

Điểm quan trọng ở đây là **đa hình (polymorphism)**: sau khi đã chọn một `Sender`, code gọi `sender.send(...)` trực tiếp theo contract. Chuyển từ `EmailSender` sang `PushSender` là thay implementation, không biến tên method thành chuỗi.

### Ví dụ Java 17+ chạy được

Lưu file **`ClearApiDemo.java`**:

```java
import java.util.Map;

public class ClearApiDemo {
    enum Channel { EMAIL, PUSH }

    interface Sender {
        void send(String recipient, String body);
    }

    static final class EmailSender implements Sender {
        @Override
        public void send(String recipient, String body) {
            System.out.println("EMAIL|" + recipient + "|" + body);
        }
    }

    static final class PushSender implements Sender {
        @Override
        public void send(String recipient, String body) {
            System.out.println("PUSH|" + recipient + "|" + body);
        }
    }

    static final class NotificationService {
        private final Map<Channel, Sender> senders;

        NotificationService(Map<Channel, Sender> senders) {
            this.senders = Map.copyOf(senders);
        }

        void send(Channel channel, String recipient, String body) {
            Sender sender = senders.get(channel);
            if (sender == null) {
                throw new IllegalArgumentException(
                        "Unsupported channel: " + channel);
            }
            sender.send(recipient, body);
        }
    }

    public static void main(String[] args) {
        NotificationService service = new NotificationService(Map.of(
                Channel.EMAIL, new EmailSender(),
                Channel.PUSH, new PushSender()
        ));

        service.send(Channel.EMAIL, "lan@example.com", "Hello");
        service.send(Channel.PUSH, "device-42", "Update");
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 ClearApiDemo.java
java ClearApiDemo
```

Kết quả chính xác:

```text
EMAIL|lan@example.com|Hello
PUSH|device-42|Update
```

Giải thích:

1. Caller chỉ biết nghiệp vụ `send(Channel, String, String)`, không cần biết các tên method nội bộ hoặc cấu trúc class implementation.
2. `Map.of(...)` thiết lập registry hai kênh. `Map.copyOf(...)` tạo bản map không thể sửa qua service; điều đó **không** biến bản thân các sender thành immutable hay thread-safe.
3. `NotificationService.send(...)` chọn implementation theo `Channel` rồi gọi `Sender.send(...)` với chữ ký tường minh. Không có `Class.getMethod` hay `Method.invoke`.
4. Nếu sau này thêm kênh SMS, có thể thêm `Channel.SMS`, triển khai `SmsSender implements Sender` và đăng ký. Compiler kiểm tra `SmsSender` thực hiện đủ method của interface.
5. Việc `Map` thiếu một kênh được xử lý tại service bằng `IllegalArgumentException`. Thiết kế thực tế có thể thêm validation recipient/body, audit, retry hoặc domain error tùy nhu cầu, nằm tại các ranh giới rõ ràng.

Với ứng dụng rất nhỏ có vài nhánh ổn định, `switch` trên enum cũng là lựa chọn hợp lệ. Không cần dựng nhiều class hoặc registry chỉ để tránh một biểu thức `switch` đơn giản. Mục tiêu là API **đúng mức trừu tượng**, không phải tạo thêm abstraction cho đẹp.

## 5. Chọn công cụ thay thế theo hợp đồng API

Điểm xuất phát là **dữ liệu và thao tác nào cần được công bố cho caller**, không phải cố loại bỏ mọi dòng Reflection. Trong ví dụ gửi thông báo, caller biết hành động `send` và kiểu `Channel`; việc chọn `EmailSender` hay `PushSender` thuộc trách nhiệm của `NotificationService`. Khi yêu cầu khác đi, lựa chọn cũng khác:

| Nhu cầu thật sự | Cơ chế phù hợp | Hợp đồng giữ được |
| --- | --- | --- |
| Nhiều implementation làm cùng một nghiệp vụ | Interface và đa hình; Strategy nếu chọn theo ngữ cảnh | `Sender.send(String, String)` được compiler kiểm tra |
| Cùng một hành vi nhận vài dạng dữ liệu đã biết khi biên dịch | Overload, generic hoặc phương thức có tên riêng | Caller được kiểm tra chữ ký; tránh `Object...` vô nghĩa |
| Chọn và tạo một implementation từ cấu hình có kiểm soát | Factory, DI hoặc `switch` với registry nhỏ | Caller nhận kiểu `Sender`, không cần biết constructor nội bộ |
| Thêm provider có cùng contract sau khi ứng dụng được đóng gói | Registry/plugin mechanism, có thể dùng `ServiceLoader<Sender>` | Plugin vẫn phải đáp ứng interface và chính sách đăng ký |
| Công bố dữ liệu qua ranh giới module/dịch vụ | DTO, `record`, getter hoặc mapper tường minh | Chỉ lộ trường dữ liệu nằm trong contract, không mở private state |

Ví dụ, method `void write(String text)` và `void write(byte[] bytes)` có thể là hai overload hợp lệ; nếu mỗi nhánh đại diện một hành vi nghiệp vụ hoàn toàn khác, đặt tên cụ thể hơn thay vì ép thành một `execute(Object)`. Với dữ liệu trao đổi, `record UserSummary(String displayName, int points) {}` thể hiện schema rõ hơn việc tự phản chiếu mọi field private của domain object.

Một registry có khóa chuỗi vẫn cần kiểm tra key, quyền và trùng lặp đăng ký. `ServiceLoader` chỉ tìm **provider đã khai báo** trong classpath/module có thể nhìn thấy; nó không tự quét mọi class. Registry/factory cũng không được biến mọi implementation thành một "mega-interface" với hàng chục thao tác không liên quan. Với hai nhánh ổn định, `switch` có thể rõ ràng hơn một plugin framework.

## 6. Khi nào Reflection vẫn có lý do chính đáng?

Reflection phù hợp khi **cấu trúc của type hoặc member thực sự chỉ biết lúc chạy**: serializer/ORM đọc metadata của model bất kỳ; DI/framework phân tích constructor và annotation; công cụ test, debugger hoặc inspector quan sát lớp không biết trước; plugin loader xử lý metadata class mới; adapter tương thích API bên thứ ba có khác biệt giữa các phiên bản.

Ở các trường hợp này, hãy **cô lập bước phản chiếu tại boundary thích hợp**. Chẳng hạn plugin loader có thể dùng Reflection để xác minh class và tạo instance, nhưng sau khi nhận được `Sender` thì phần nghiệp vụ gọi trực tiếp `sender.send(...)`. Các thư viện thao tác private member cần giới hạn quyền truy cập và JPMS `opens`; dispatcher chọn hành động từ request cần allowlist, authorization và schema validation. Thao tác Reflection nào lặp lại nhiều có thể cache metadata đã kiểm tra, nhưng không được cache một quyết định cấp quyền chung cho mọi người dùng.

Nếu class/method đã biết tại compile time mà code vẫn tự tìm chúng bằng tên chuỗi, hãy xem lại hợp đồng trước. Ngược lại, nếu bài toán thật sự là khám phá field/method/annotation của những kiểu chưa biết, một API typed duy nhất không thay được khả năng introspection đó.

## 7. Dùng MethodHandle không tự sửa được thiết kế API mơ hồ

`java.lang.invoke.MethodHandle` và `VarHandle` có những điểm mạnh: thao tác có mô tả kiểu rõ, linh hoạt khi liên kết runtime, hỗ trợ một số tối ưu và memory access khác với Reflection truyền thống.

Tuy nhiên nếu ứng dụng có đầy đủ thông tin để viết:

```java
userService.activate(userId);
```

mà lại xây đường đi:

```text
"activate" -> tìm MethodHandle theo tên -> invoke -> xử lý mọi lỗi kiểu runtime
```

thì việc đổi công cụ từ `Method.invoke` sang `MethodHandle.invoke` không giải quyết vấn đề hợp đồng thiết kế. Cùng một nghiệp vụ vẫn bị chọn bằng chuỗi; lỗi thiếu method vẫn chuyển sang runtime và caller vẫn khó biết phạm vi hành động hợp lệ.

Chọn cơ chế invoke bằng lý do cụ thể: framework/VM integration, call site thực sự động, hoặc dữ liệu benchmark. Đừng chọn Reflection/MethodHandle chỉ để né việc tạo interface, method overload hay adapter cần thiết.

## 8. API rõ ràng giúp bảo vệ ranh giới module và quyền truy cập

Một module tốt thường công bố những gì bên ngoài **được phép làm**, thay vì để caller truy cập tất cả chi tiết triển khai. Ví dụ, `AccountService.closeAccount(accountId)` thể hiện điều kiện nghiệp vụ; việc truy cập field private `status` bằng Reflection rồi tự đổi thành `CLOSED` có thể bỏ qua validation, audit, event hoặc transaction.

Một ranh giới phù hợp:

```text
HTTP / UI / CLI
     |
     v
AccountService.closeAccount(accountId)
     |
     +-- kiểm tra quyền và trạng thái
     +-- thực thi nghiệp vụ/transaction
     +-- ghi audit / phát sự kiện nếu cần
     |
     v
Domain / Persistence
```

Nếu caller dùng `Field.setAccessible(true)` để đổi trạng thái, nó có thể phá vỡ invariants. Với Java module system, `exports` công bố package để truy cập public API, còn `opens` cho phép mức truy cập reflective theo các điều kiện liên quan. Không mở toàn bộ package chỉ vì muốn dùng một field private từ client, trừ khi framework thực sự cần và phạm vi mở đã được cân nhắc.

Một API tường minh còn tạo nơi rõ ràng để áp dụng authorization. Đừng cho chuỗi do người dùng gửi thẳng vào tên method Reflection trên service nội bộ: ngay cả khi một số method được gọi thành công, đó không phải cơ chế kiểm soát hành động nghiệp vụ được thiết kế nghiêm túc.

## 9. Di chuyển từ Reflection dispatcher sang API rõ ràng

Nếu code hiện có đang dựa vào `invoke(name, args)`, có thể chuyển dần mà vẫn giữ behavior đang dùng:

1. **Liệt kê tất cả action thực tế** từ caller/config và test. Ghi rõ tên nghiệp vụ, kiểu input/output, lỗi và permission. Phân biệt action tĩnh với điểm mở rộng thật sự động.
2. **Nhóm các action theo contract**. Nếu nhiều implementation làm cùng việc, tạo interface. Nếu chỉ một số thao tác trên cùng service, thêm method public chuyên trách hoặc overload phù hợp. Không ép nhiều nghiệp vụ khác nhau vào một generic method.
3. **Chọn điểm dispatch typed**. Caller truyền enum hoặc một value object được validate; service dùng `switch`/factory/registry để chọn implementation.
4. **Đưa validation và lỗi về đúng ranh giới**. Kiểm tra dữ liệu đầu vào, unknown action, unsupported version, permission trước khi gọi service. Giữ logic nghiệp vụ ở nơi dễ test.
5. **Thêm test hành vi trước khi thay đường gọi**. Dùng case hợp lệ, sai action, dữ liệu thiếu, exception từ implementation và quyền truy cập; so sánh output và tác dụng phụ.
6. **Thay caller dần**. Nếu phải giữ API chuỗi cho backward compatibility, tạo một adapter nhỏ để parse key thành enum rồi chuyển sang service typed; không lan truyền tên Java method ra các lớp khác.
7. **Xóa dispatcher dư thừa sau khi không còn caller**. Không để song song hai đường thực thi mà một đường bỏ qua validation/audit.

Ví dụ adapter chuyển đổi ở ranh giới, thay vì gọi member Java theo chuỗi:

```java
Channel parseChannel(String text) {
    return switch (text) {
        case "email" -> Channel.EMAIL;
        case "push" -> Channel.PUSH;
        default -> throw new IllegalArgumentException("Unknown channel: " + text);
    };
}
```

Đây là **method minh họa** trong class đã khai báo enum `Channel`, không phải file chạy độc lập. Với `text == null`, `switch` sẽ ném `NullPointerException` trong dạng này; API production nên xác định riêng cách xử lý input null. Ý nghĩa của đoạn code là: parse/validate chuỗi bên ngoài thành kiểu domain một lần; từ đó trở vào, caller dùng kiểu tường minh.

## 10. So sánh hai lựa chọn ở những điểm quan trọng

| Tiêu chí | Gọi member theo chuỗi bằng Reflection | API typed + interface/factory |
| --- | --- | --- |
| Kiểu và chữ ký | Tra cứu/kiểm tra chủ yếu runtime | Compiler kiểm tra phần lớn tại call site |
| Đổi tên method | Chuỗi có thể bị bỏ sót khi refactor | Công cụ đổi tên và compiler hỗ trợ tốt |
| Quyền truy cập | Cần giải quyết access/member/module riêng | Public contract xác định rõ ranh giới sử dụng |
| Lỗi | Có lỗi lookup/invoke, `InvocationTargetException` | Lỗi nghiệp vụ thể hiện trực tiếp hơn |
| Khả năng test | Cần bao phủ từng tên/signature chuỗi | Test theo contract và implementation |
| Tính động | Truy cập thành viên runtime linh hoạt | Chọn implementation runtime qua factory/DI/registry vẫn được |
| Hiệu năng | Có chi phí lookup/invoke; cache có thể giảm lookup | Thường dễ tối ưu và đo hơn, nhưng cần benchmark cho từng bài toán |
| Trường hợp hợp lý | Framework/tooling khám phá metadata thật sự động | Logic nghiệp vụ và tích hợp có contract đã biết |

Bảng là gợi ý lựa chọn kiến trúc, **không** cam kết mọi đường code không dùng Reflection đều nhanh hơn mọi đường có Reflection. JIT, cách gọi, workload và thiết kế cache đều có thể ảnh hưởng. Điều quan trọng là chi phí và tính rõ ràng của hệ thống phải phù hợp nhu cầu.

## 11. Dấu hiệu nên xem lại thiết kế

Nếu gặp các mẫu sau, hãy kiểm tra liệu API tường minh có phù hợp hơn:

- Một service nhận `String methodName`/`Object[] args` chỉ để chọn trong vài method cố định.
- Dùng `getDeclaredField` + `setAccessible(true)` để đọc/ghi state mà module đáng lẽ cung cấp method/DTO rõ ràng.
- Dùng Reflection để khởi tạo những class được biết lúc compile time thay vì constructor/factory/DI.
- Định nghĩa các action kinh doanh bằng tên method Java trong database/API request rồi tự tạo quyền gọi.
- Sau mỗi lần đổi tên method, phải tìm nhiều chuỗi hard-code trên toàn hệ thống.
- Phần lớn code xử lý `ReflectiveOperationException`, cast runtime và kiểm tra signature thay vì xử lý nghiệp vụ.
- Thêm một chức năng buộc phải dán nhiều chuỗi tên Java vào config, dispatcher và UI dù tập chức năng được quản lý tập trung.

Không phải mọi trường hợp xuất hiện một dòng Reflection đều là lỗi thiết kế. Đánh giá dựa trên **phạm vi tính động có thật** và liệu abstraction mới có giảm gánh nặng người đọc lẫn bảo trì hay không.

## 12. Lỗi thường gặp khi refactor

**Thay Reflection bằng một “mega-interface”.** Nếu mọi implementation phải triển khai hàng chục method không liên quan, hợp đồng quá lớn. Hãy tách interface theo khả năng (interface segregation).

**Dùng enum cho plugin không giới hạn.** `enum` thích hợp với tập lựa chọn đóng. Nếu cần provider bên thứ ba được cài thêm runtime, dùng registry/ServiceLoader/extension point typed. Đừng bắt sửa mã lõi chỉ để thêm mỗi plugin khi yêu cầu thực sự là mở rộng động.

**Dùng Object ở mọi API để khỏi Reflection.** `Object execute(Object input)` không tự tốt hơn `Method.invoke` nếu caller vẫn phải đoán kiểu/cast theo quy ước không được công bố. Ưu tiên request/response types rõ ràng; dùng generic hoặc sealed hierarchy khi phù hợp.

**Đưa validation vào controller mà bỏ qua service.** Đổi từ reflective call sang direct call không bảo đảm authorization/invariants. Service phải bảo vệ ranh giới nghiệp vụ phù hợp, kể cả khi có caller ngoài HTTP.

**Không tách adapter legacy.** Nếu bắt buộc nhận tên cũ qua JSON/config, hãy parse và validate tại boundary. Giữ một adapter có kiểm soát rồi cho phần lõi hoạt động trên contract typed.

**Tự tạo registry phức tạp khi chỉ có một nhánh.** API tốt nhất đôi khi chỉ là một method đặt tên rõ ràng. Đánh đổi abstraction lấy tính dễ hiểu, đừng dựng plugin framework để thay thế một lời gọi bình thường.

## 13. Tự kiểm tra và bài tập

1. Hệ thống có ba công thức thuế cố định, chọn theo mã quốc gia. Bạn sẽ chọn `switch`, `Strategy` hay Reflection? Giải thích dựa trên mức độ thay đổi và nhu cầu mở rộng.
2. Một plugin được nạp sau khi ứng dụng khởi động, nhưng plugin phải tuân thủ `ReportExporter.export(Report)`. Vì sao registry/ServiceLoader với contract typed vẫn hỗ trợ tính động?
3. Chỉ ra ba lỗi mà compiler có thể bắt khi gọi `service.send(Channel.EMAIL, String, String)`, nhưng khó bắt sớm với `invoke("sendEmail", Object...)`.
4. Tại sao `MethodHandle` không tự giải quyết vấn đề nếu tên method vẫn lấy từ request của người dùng?
5. Một framework serializer cần truy cập nhiều field của những class không biết trước lúc biên dịch. Đây có phải lý do hợp lý để dùng Reflection? Cần giới hạn quyền/kiểm tra dữ liệu như thế nào?
6. Nếu chuyển hệ thống từ `getDeclaredMethod` sang interface, cần test những gì để bảo toàn hành vi, lỗi, permission và tính tương thích?
7. Từ ví dụ `ClearApiDemo`, thêm một implementation SMS. Bạn muốn thêm enum value hay tạo plugin registry? Điều kiện nào khiến lựa chọn thay đổi?

**Kết quả cần đạt:** nhận ra sự khác nhau giữa nhu cầu **liên kết động thật sự** và việc dùng Reflection để né thiết kế contract; biết ưu tiên interface, overload, factory, DTO, registry hoặc ServiceLoader phù hợp; đồng thời giữ Reflection trong những thành phần thật sự cần khám phá metadata runtime, với ranh giới quyền truy cập và lỗi rõ ràng.
