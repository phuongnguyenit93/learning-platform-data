# Kết hợp kiểu trả về đồng biến với giao diện

## 1. Interface chung và interface chuyên biệt

Một interface chung có thể hứa trả về một kiểu tổng quát, trong khi interface chuyên biệt biết chắc kết quả thuộc một kiểu con. Java cho phép khai báo lại phương thức trong interface con với kiểu trả về cụ thể hơn, nếu kiểu đó thay thế được kiểu trả về của hợp đồng cha.

Ví dụ ý tưởng:

```text
MessageFactory.create(text) → Message
           ↑
EmailFactory.create(text)   → EmailMessage

EmailMessage triển khai Message
EmailFactory mở rộng MessageFactory
```

Bên cần một MessageFactory vẫn dùng được EmailFactory: kết quả EmailMessage cũng là Message. Bên cần thông tin dành riêng cho email có thể phụ thuộc EmailFactory và nhận kiểu EmailMessage ngay khi biên dịch. [JLS: yêu cầu ghi đè trong interface](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1.2)

Đây là **kiểu trả về đồng biến (covariant return type)** kết hợp với quan hệ mở rộng interface. Nó làm mạnh thêm cam kết về kiểu kết quả; không yêu cầu phương thức có một tên mới.

## 2. Hai nơi có thể thu hẹp kiểu trả về

| Nơi khai báo | Cách áp dụng |
| --- | --- |
| Interface con mở rộng interface cha | Khai báo lại cùng phương thức, trả kiểu con phù hợp |
| Lớp triển khai interface | Cung cấp phương thức public, trả cùng kiểu hoặc kiểu con phù hợp |

Nếu chỉ lớp triển khai thu hẹp kết quả, bên gọi qua interface chung vẫn chỉ thấy kiểu kết quả chung. Nếu muốn API chuyên biệt được công bố qua một interface, hãy đưa lời hứa cụ thể vào interface chuyên biệt ấy.

Phương thức ghi đè phải có chữ ký phù hợp. Đổi danh sách kiểu tham số để nhận một kiểu hẹp hơn không phải cơ chế đồng biến kết quả; điều đó có thể tạo một phương thức nạp chồng khác.

## 3. Chương trình đầy đủ: nhà máy tạo thông điệp email

Lưu vào **InterfaceCovarianceDemo.java**:

```java
import java.util.Objects;

public class InterfaceCovarianceDemo {
    interface Message {
        String text();
    }

    record EmailMessage(String text, String recipient)
            implements Message {
        EmailMessage {
            Objects.requireNonNull(text, "text");
            Objects.requireNonNull(recipient, "recipient");
        }
    }

    interface MessageFactory {
        Message create(String text);
    }

    interface EmailFactory extends MessageFactory {
        @Override
        EmailMessage create(String text);
    }

    static class DefaultEmailFactory implements EmailFactory {
        private final String recipient;

        DefaultEmailFactory(String recipient) {
            this.recipient =
                    Objects.requireNonNull(recipient, "recipient");
        }

        @Override
        public EmailMessage create(String text) {
            return new EmailMessage(text, recipient);
        }
    }

    public static void main(String[] args) {
        EmailFactory specific =
                new DefaultEmailFactory("lan@example.com");
        EmailMessage email = specific.create("Ready");

        System.out.println("specificText=" + email.text());
        System.out.println("recipient=" + email.recipient());

        MessageFactory general = specific;
        Message message = general.create("Queued");

        System.out.println("generalText=" + message.text());
        System.out.println("runtimeType="
                + message.getClass().getSimpleName());

        printText(general);

        if (message instanceof EmailMessage detailed) {
            System.out.println("checkedRecipient="
                    + detailed.recipient());
        }
    }

    private static void printText(MessageFactory factory) {
        Message result = factory.create("Shared");
        System.out.println("sharedText=" + result.text());
    }
}
```

Biên dịch và chạy bằng JDK hỗ trợ Java 17:

```shell
javac --release 17 -encoding UTF-8 InterfaceCovarianceDemo.java
java InterfaceCovarianceDemo
```

Kết quả:

```text
specificText=Ready
recipient=lan@example.com
generalText=Queued
runtimeType=EmailMessage
sharedText=Shared
checkedRecipient=lan@example.com
```

Chương trình chỉ tạo dữ liệu thông điệp để học quan hệ kiểu, không thực hiện gửi email.

### Theo dõi ba tầng hợp đồng

1. MessageFactory công bố kết quả Message.
2. EmailFactory thu hẹp kết quả thành EmailMessage.
3. DefaultEmailFactory thực hiện đúng cam kết của EmailFactory.

Phương thức `printText` chỉ cần MessageFactory và Message, nên vẫn dùng được cùng đối tượng nhà máy. Nó không cần biết trường recipient của EmailMessage.

Trong record EmailMessage, phương thức truy cập `text()` do record cung cấp đáp ứng Message. Việc kiểm tra null là quy tắc của dữ liệu trong ví dụ; bản thân đồng biến kiểu trả về không tự thêm kiểm tra đó.

## 4. Kiểu biến ở bên gọi vẫn quan trọng

Cùng một đối tượng nhà máy có thể được tham chiếu qua hai interface:

```java
EmailMessage first = specific.create("First");
Message second = general.create("Second");
```

Đây là đoạn minh họa để đặt trong `main` của chương trình trên.

Kiểu tĩnh EmailFactory cho biết `create` trả EmailMessage. Kiểu tĩnh MessageFactory chỉ công bố Message. Việc đối tượng thực tế là DefaultEmailFactory không làm mọi lời gọi qua interface cha tự có kiểu kết quả chuyên biệt.

Nếu thêm dòng sau vào `main`, nó không biên dịch:

```java
EmailMessage wrong = general.create("Wrong");
```

Đây là đoạn cố ý không hợp lệ: thông tin ở interface cha chưa đủ để gán trực tiếp sang EmailMessage. Nếu chỉ cần đọc text, giữ Message là phù hợp. Nếu thực sự cần khả năng email, dùng interface chuyên biệt từ đầu hoặc kiểm tra kiểu kết quả tại một ranh giới hợp lý.

### Vì sao không giữ kiểu trả về rộng ở lớp triển khai?

Nếu DefaultEmailFactory khai báo `public Message create(String text)`, nó chưa đáp ứng hợp đồng EmailFactory yêu cầu EmailMessage, dù thân phương thức thực tế luôn tạo EmailMessage.

Trình biên dịch kiểm tra **khai báo**, không dùng mọi chi tiết trong thân để suy luận rằng phương thức đã hứa kiểu hẹp hơn. Việc viết `return new EmailMessage(...)` không sửa kiểu trả về đã khai báo.

## 5. Một phương thức đáp ứng nhiều interface

Khi hai interface có cùng chữ ký phương thức, lớp triển khai không viết hai phương thức chỉ khác kiểu trả về. Một phương thức duy nhất có thể đáp ứng cả hai nếu kiểu trả về của nó phù hợp với cả hai hợp đồng.

Ví dụ:

- Một interface cần `CharSequence read()`.
- Interface khác cần `Serializable read()`.
- String triển khai cả CharSequence và Serializable.
- Phương thức `String read()` có thể đáp ứng cả hai.

String không cần nằm trong một quan hệ cha–con duy nhất giữa hai interface kết quả; nó phải là kiểu đáp ứng được **cả hai**. [API String: các interface triển khai](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)

### Chương trình kết hợp hai hợp đồng

Lưu thành **CombinedInterfaceReturnDemo.java**:

```java
import java.io.Serializable;

public class CombinedInterfaceReturnDemo {
    interface TextSource {
        CharSequence read();
    }

    interface SerializableSource {
        Serializable read();
    }

    interface StringSource
            extends TextSource, SerializableSource {
        @Override
        String read();
    }

    static class FixedSource implements StringSource {
        @Override
        public String read() {
            return "Ready";
        }
    }

    public static void main(String[] args) {
        StringSource specific = new FixedSource();
        String text = specific.read();
        System.out.println("specificLength=" + text.length());

        TextSource asText = specific;
        CharSequence sequence = asText.read();
        System.out.println("textView=" + sequence);

        SerializableSource asSerializable = specific;
        Serializable serializable = asSerializable.read();
        System.out.println("serializableType="
                + serializable.getClass().getSimpleName());
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 CombinedInterfaceReturnDemo.java
java CombinedInterfaceReturnDemo
```

Kết quả:

```text
specificLength=5
textView=Ready
serializableType=String
```

StringSource khai báo rõ kết quả String để thống nhất hai hợp đồng. FixedSource chỉ cần một thân `read()`. Bên gọi qua từng interface vẫn thấy kiểu kết quả mà interface ấy công bố. [JLS: phương thức kế thừa có chữ ký tương đương ghi đè](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1.3)

Nếu hai hợp đồng yêu cầu các kiểu trả về không thể cùng được đáp ứng, không thể chọn một phương thức bất kỳ rồi hy vọng trình biên dịch dựa vào đối tượng thực tế. Ví dụ, hai yêu cầu `String read()` và `Integer read()` không thể được thống nhất bằng một kiểu con chung trong Java vì String và Integer là các lớp final khác nhau.

## 6. Những quy tắc không được bỏ qua

### Phương thức triển khai phải có quyền truy cập phù hợp

Các phương thức abstract trong các interface ví dụ là public. Phương thức của lớp triển khai phải public; bỏ từ khóa public sẽ làm quyền truy cập hẹp hơn, gây lỗi. Kiểu trả về hẹp hơn không cho phép thu hẹp quyền truy cập.

### Giữ đúng chữ ký, không chỉ tên

Nếu interface có `Message create(String text)`, một phương thức `EmailMessage create(Object text)` hay `EmailMessage create()` không trực tiếp thực hiện hợp đồng đó. Dùng `@Override` để trình biên dịch phát hiện nhầm lẫn. [API Override](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Override.html)

### Không phân biệt hai overload chỉ bằng kết quả

Không đặt hai phương thức `Message create(String)` và `EmailMessage create(String)` làm hai overload độc lập trong cùng lớp. Tác giả chỉ khai báo phương thức thực hiện với kết quả hẹp phù hợp; cơ chế ngôn ngữ chịu trách nhiệm duy trì hợp đồng ghi đè.

### Checked exception vẫn theo quy tắc riêng

Nếu interface không cho phép một checked exception, lớp triển khai không tự thêm nó chỉ vì đã thu hẹp kiểu kết quả. Cần đồng thời xét chữ ký, quyền truy cập và các ngoại lệ. [JLS: yêu cầu khi ghi đè](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3)

### Không tự giải quyết xung đột default method

Hai ví dụ ở bài dùng các phương thức hợp đồng abstract. Nếu hai interface mang các default method xung đột, chỉ kiểm tra quan hệ kiểu trả về là chưa đủ; lớp/interface kết hợp còn phải giải quyết quy tắc lựa chọn phần thực hiện. Đừng coi đồng biến kết quả là cơ chế chọn tùy ý một thân default.

## 7. Phân biệt với tham số hóa interface bằng generic

Một thiết kế khác có thể viết hợp đồng như:

```java
interface Factory<T> {
    T create();
}

final class StringFactory implements Factory<String> {
    @Override
    public String create() {
        return "Ready";
    }
}
```

Đây là các khai báo độc lập có thể biên dịch, không có `main`.

Trong ngữ cảnh `Factory<String>`, T đã được liên kết với String. Vì vậy việc phương thức triển khai trả String trước hết thể hiện phép thay thế đối số kiểu trong hợp đồng generic. Không nên giải thích mọi kiểu trả về cụ thể trong một implementation như thể nó luôn xuất phát từ một interface con thu hẹp kiểu.

Có thể kết hợp hai kỹ thuật, nhưng cần hiểu riêng:

- Generic biểu đạt một họ hợp đồng theo đối số kiểu.
- Interface chuyên biệt với kết quả đồng biến biểu đạt một cam kết kết quả cụ thể hơn trong quan hệ mở rộng.

Nếu kết quả là collection, phải xét quan hệ kiểu của toàn bộ collection. Ví dụ, Dog là Animal không làm List<Dog> thành kiểu con của List<Animal>. Không dùng đồng biến phương thức để bỏ qua tính chất của kiểu generic.

## 8. Chọn thiết kế theo nhu cầu bên sử dụng

Hãy công bố interface chung khi bên sử dụng chỉ cần năng lực chung. Tạo interface chuyên biệt khi có một nhóm bên sử dụng cần dựa vào cam kết kết quả cụ thể và cam kết đó ổn định trong miền bài toán.

Cần giữ ý nghĩa hành vi nhất quán. Nếu `create(text)` của hợp đồng chung hứa giữ nguyên text, implementation chuyên biệt vẫn phải giữ lời hứa đó; kiểu trả về đúng chưa đủ để chứng minh hành vi đúng. Cũng không tự thay đổi quy tắc null, tài nguyên hay tác dụng phụ chỉ vì đổi kiểu kết quả.

Khi đọc hoặc thiết kế API, đặt bốn câu hỏi:

1. Interface cha hứa kiểu và hành vi gì?
2. Kiểu kết quả của interface/lớp con có đáp ứng lời hứa ấy không?
3. Bên gọi sẽ sử dụng interface chung hay interface chuyên biệt?
4. Có nhiều hợp đồng, generic hoặc default method cần xét thêm không?

### Tự thực hành

1. Bỏ khai báo `create` khỏi EmailFactory nhưng giữ implementation trả EmailMessage. Biến có kiểu EmailFactory còn thấy kiểu trả về nào? Vì sao?
2. Giữ EmailFactory như cũ, đổi implementation thành trả Message. Giải thích lỗi dù thân vẫn tạo EmailMessage.
3. Trong ví dụ thứ hai, đổi `String read()` ở FixedSource thành `CharSequence read()`. Vì sao chưa đáp ứng StringSource?
4. Bỏ public ở một phương thức triển khai và kiểm tra lỗi truy cập.
5. Thiết kế một interface nhà máy tài liệu chung và interface chuyên tạo báo cáo. Viết lời gọi qua cả hai kiểu, không dùng ép kiểu để thay cho khai báo hợp đồng đúng.
6. Chỉ ra trong hai chương trình đâu là quan hệ kiểu của kết quả và đâu là kiểu tĩnh của biến giữ nhà cung cấp.
