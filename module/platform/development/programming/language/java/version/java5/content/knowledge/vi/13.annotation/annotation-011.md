# @Override và kiểm tra ý định ghi đè

## Khái niệm: ghi rõ điều ta muốn trình biên dịch xác nhận

Ghi đè (overriding) là việc một kiểu con cung cấp khai báo phương thức phù hợp với phương thức ở kiểu cha theo các quy tắc của Java. Nó cho phép cùng một lời gọi phương thức thực thi hành vi phù hợp với đối tượng thực tế.

`@Override` ghi rõ ý định: **phương thức này phải thực sự ghi đè hoặc triển khai một phương thức của kiểu cha**. Trình biên dịch kiểm tra ý định đó và báo lỗi nếu khai báo không phù hợp.

Annotation này đặc biệt hữu ích khi tên hoặc kiểu tham số bị viết sai, hoặc khi chữ ký phương thức ở kiểu cha thay đổi. Một lỗi vốn có thể âm thầm tạo phương thức khác sẽ trở thành lỗi biên dịch ngay tại nơi khai báo.

`@Override` thuộc `java.lang`, nên không cần import. Đây vẫn là cách viết phù hợp trong Java hiện đại, bao gồm mã triển khai interface. Các ví dụ trong bài chạy trên JDK 17 trở lên và không cần thư viện ngoài.

## Vì sao cần annotation khi Java đã có quy tắc ghi đè?

So sánh hai ý định:

- “Tôi muốn thêm một phương thức mới có tên `describe`.”
- “Tôi muốn thay thế cách thực thi `describe(String)` đã có ở lớp cha.”

Nếu chỉ nhìn khai báo phương thức, trình biên dịch không thể luôn đoán được người viết đang muốn gì. Một phương thức cùng tên nhưng khác kiểu tham số có thể là nạp chồng hợp lệ.

Ví dụ, lớp cha có `describe(String)`, lớp con viết `describe(Object)`. Hai khai báo có thể cùng tồn tại dưới dạng nạp chồng (overloading). Việc `Object` là kiểu cha của `String` không khiến `describe(Object)` ghi đè `describe(String)`.

Thêm `@Override` vào phương thức lớp con biến ý định ghi đè thành yêu cầu được kiểm tra. Khi trình biên dịch báo lỗi, cần sửa mối quan hệ giữa các khai báo; không nên xóa annotation chỉ để làm lỗi biến mất.

## Cơ chế và vòng đời của @Override

Theo [API Override](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Override.html), annotation có đích áp dụng là `METHOD` và chính sách lưu giữ `SOURCE`.

Điều đó dẫn đến ba điểm thực hành:

1. Đặt `@Override` trên khai báo phương thức.
2. Trình biên dịch dùng nó để kiểm tra trong quá trình biên dịch.
3. Nó không được lưu như annotation của phương thức trong tệp `.class`, nên reflection lúc chạy không đọc được `@Override` trên phương thức đó.

Không thể gắn `@Override` vào constructor, field hay lớp. Constructor không phải phương thức được thừa kế rồi ghi đè.

`@Override` cũng không bật hay tắt đa hình. Nếu hai phương thức đã có quan hệ ghi đè hợp lệ, việc bỏ annotation không làm quan hệ đó biến mất. Annotation bổ sung khả năng kiểm tra ý định và giúp người đọc nhận ra quan hệ nhanh hơn.

### Phạm vi hợp lệ rộng hơn “chỉ ghi đè lớp cha trực tiếp”

Các tình huống thông dụng gồm:

- Ghi đè phương thức của lớp cha, kể cả được thừa kế qua nhiều cấp.
- Triển khai phương thức được yêu cầu bởi interface.
- Ghi đè phương thức như `toString()`, `equals(Object)` hoặc `hashCode()` của `Object`.
- Ghi đè phương thức `default` được thừa kế từ interface khi các quy tắc ngôn ngữ cho phép.

Chi tiết đặc tả còn cho phép annotation trên khai báo có chữ ký tương đương ghi đè với phương thức public của `Object`; chẳng hạn một interface có thể khai báo lại `boolean equals(Object other)` với `@Override`. Vì vậy, không nên giản lược thành quy tắc “chỉ dùng trong lớp con có `extends`”.

Xem điều kiện chính xác tại [JLS §9.6.4.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.4).

## Những điều kiện phải hiểu trước khi sửa lỗi

### Tên và tham số phải tạo được quan hệ ghi đè

Với các phương thức không generic thông thường, cần cùng tên và cùng danh sách kiểu tham số theo thứ tự. Tên biến tham số không quyết định quan hệ đó: `format(String value)` và `format(String text)` có thể tương ứng với nhau.

Không thể đổi `String` thành `Object`, `int` thành `Integer`, hay thêm một tham số rồi vẫn mặc nhiên gọi đó là ghi đè. Boxing và khả năng chuyển đổi đối số khi gọi phương thức không thay thế quy tắc chữ ký khi khai báo.

Với kiểu generic, phải xét tham số kiểu sau khi được gắn vào kiểu cụ thể. Ví dụ, triển khai `Formatter<String>` yêu cầu `format(String)` nếu interface khai báo `format(T)`. Đừng tự thay bằng `format(Object)` chỉ vì biết Java có xóa kiểu (type erasure); hãy để trình biên dịch kiểm tra khai báo với `@Override`.

### Kiểu trả về phải tương thích

Kiểu trả về không phải thành phần để tạo nạp chồng. Không thể có hai phương thức chỉ khác kiểu trả về mà cùng chữ ký trong một lớp.

Khi ghi đè, Java cho phép kiểu trả về hiệp biến (covariant return): với kiểu tham chiếu phù hợp, phương thức lớp con có thể trả kiểu cụ thể hơn. Chẳng hạn phương thức cha trả `Object`, phương thức con trả `String`.

Không áp dụng quy tắc đó để tùy ý đổi kiểu nguyên thủy, ví dụ từ `int` sang `long`.

### Không thu hẹp quyền truy cập hoặc mở rộng ngoại lệ được kiểm tra

Phương thức ghi đè không được giảm khả năng truy cập. Nếu phương thức cha là `public`, phương thức con cũng phải là `public`. Phương thức trừu tượng thông thường được khai báo trong interface là `public`, nên phương thức triển khai trong lớp không được bỏ `public` để thành package-private.

Phương thức ghi đè cũng không được khai báo ngoại lệ được kiểm tra (checked exception) rộng hơn những gì hợp đồng của phương thức cha cho phép. Ví dụ, nếu phương thức cha cho phép `IOException`, phương thức con có thể bỏ `throws` hoặc dùng một ngoại lệ con thích hợp, nhưng không thể đổi thành `throws Exception`.

Đây là ràng buộc của ngôn ngữ. `@Override` không miễn trừ hoặc nới lỏng các ràng buộc đó.

### Phân biệt các trường hợp không ghi đè

| Khai báo ở kiểu cha | Điều cần nhớ |
| --- | --- |
| Phương thức instance có thể ghi đè | Có thể khai báo phương thức ghi đè nếu thỏa các điều kiện liên quan |
| Phương thức `static` | Phương thức `static` cùng chữ ký ở lớp con là che khuất (hiding), không phải ghi đè |
| Phương thức `private` | Không được thừa kế để phương thức lớp con ghi đè nó |
| Phương thức `final` | Không được ghi đè |
| Phương thức package-private ở package khác | Không thể chỉ dựa vào cùng chữ ký để kết luận có quan hệ ghi đè |
| Constructor | Không được ghi đè |

Không được thay phương thức instance bằng phương thức `static` cùng chữ ký hoặc làm ngược lại để lách các quy tắc này. Với trường hợp package-private qua package khác, cần kiểm tra đầy đủ quan hệ truy cập và các lớp trung gian, thay vì suy luận chỉ từ tên phương thức.

Các quy tắc nền tảng được mô tả tại [JLS §8.4.8](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8).

## Ví dụ chạy đầy đủ: lớp cha, interface, Object và nạp chồng

Lưu thành `OverrideDemo.java`:

```java
import java.util.Locale;

public class OverrideDemo {
    static class Processor {
        public Object convert(String input) {
            return "base:" + input;
        }
    }

    static class UpperCaseProcessor extends Processor {
        @Override
        public String convert(String input) {
            return input.toUpperCase(Locale.ROOT);
        }

        public String convert(int count) {
            return "count:" + count;
        }

        @Override
        public String toString() {
            return "UpperCaseProcessor";
        }
    }

    interface Formatter<T> {
        String format(T input);
    }

    static class BracketFormatter implements Formatter<String> {
        @Override
        public String format(String input) {
            return "[" + input + "]";
        }
    }

    public static void main(String[] args) {
        Processor processor = new UpperCaseProcessor();
        UpperCaseProcessor concrete = new UpperCaseProcessor();
        Formatter<String> formatter = new BracketFormatter();

        System.out.println("polymorphism=" + processor.convert("hello"));
        System.out.println("overload=" + concrete.convert(3));
        System.out.println("interface=" + formatter.format("java"));
        System.out.println("toString=" + concrete);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 OverrideDemo.java
java OverrideDemo
```

Kết quả:

```text
polymorphism=HELLO
overload=count:3
interface=[java]
toString=UpperCaseProcessor
```

### Giải thích mối quan hệ giữa các khai báo

`UpperCaseProcessor.convert(String)` ghi đè `Processor.convert(String)`. Phương thức cha trả `Object`, còn phương thức con trả `String`; đây là kiểu trả về hiệp biến hợp lệ.

Biến `processor` có kiểu khai báo `Processor`, nhưng đối tượng thực tế là `UpperCaseProcessor`. Sau khi lời gọi `convert("hello")` được xác định hợp lệ, việc chọn phần thực thi phương thức instance tương ứng dựa trên đối tượng thực tế. Vì thế kết quả là `HELLO`.

`UpperCaseProcessor.convert(int)` là nạp chồng với `convert(String)`. Nó không có phương thức tương ứng ở `Processor` để ghi đè, nên không được gắn `@Override` trong chương trình này.

`BracketFormatter.format(String)` triển khai phương thức của `Formatter<String>`. `@Override` là hợp lệ dù lớp dùng `implements` và không viết một lớp cha riêng bằng `extends`.

`UpperCaseProcessor.toString()` ghi đè phương thức của `Object`. Khi nối chuỗi với đối tượng `concrete`, phương thức `toString()` này cung cấp phần biểu diễn đối tượng.

### Kiểu khai báo vẫn quyết định những lời gọi có thể viết

Trong ví dụ, có thể gọi `concrete.convert(3)` vì kiểu khai báo của `concrete` là `UpperCaseProcessor`, nơi có phiên bản nhận `int`.

Nếu thay bằng `processor.convert(3)`, chương trình sẽ không biên dịch: kiểu khai báo `Processor` không cung cấp phương thức nhận `int` phù hợp. Đối tượng thực tế là lớp con không làm mọi phương thức mới của lớp con trở nên gọi được qua biến kiểu cha.

Đây là hai vấn đề riêng: chọn chữ ký khả dụng khi biên dịch và chọn phần thực thi của phương thức instance khi chạy. `@Override` không gộp hai bước đó.

## Ví dụ cố ý sai: khác tham số nhưng tưởng đã ghi đè

Đoạn dưới đây là một tệp độc lập **cố ý không biên dịch**, dùng để quan sát lỗi. Lưu thành `BrokenOverride.java`:

```java
public class BrokenOverride {
    static class Parent {
        public String describe(String text) {
            return "parent:" + text;
        }
    }

    static class Child extends Parent {
        @Override
        public String describe(Object text) {
            return "child:" + text;
        }
    }
}
```

Thử biên dịch:

```shell
javac -encoding UTF-8 BrokenOverride.java
```

Trình biên dịch sẽ báo lỗi tại `@Override` vì `Child.describe(Object)` không ghi đè `Parent.describe(String)`. Câu chữ chẩn đoán có thể khác tùy JDK và ngôn ngữ hiển thị; điểm cần quan sát là quá trình biên dịch thất bại.

Có hai hướng sửa tùy đúng ý định:

- Muốn ghi đè: đổi tham số của phương thức con thành `String text`, giữ `@Override`.
- Muốn nạp chồng: giữ `Object text`, bỏ `@Override`, rồi kiểm tra lại cách các lời gọi chọn phương thức.

Hướng thứ hai là một quyết định thay đổi thiết kế, không phải thao tác sửa lỗi máy móc. Nếu chỉ xóa annotation trong khi vẫn tưởng mình ghi đè, chương trình có thể biên dịch nhưng gọi hành vi khác dự kiến.

## Lỗi thường gặp và cách đọc chẩn đoán

### Viết nhầm equals(Object) thành equals(KieuCuThe)

Chẳng hạn trong lớp `User`, khai báo `boolean equals(User other)` tạo một phương thức khác với `equals(Object)` của `Object`. Nếu thực sự muốn ghi đè, thêm `@Override` sẽ phát hiện sai tham số.

Khai báo đúng phải có dạng `public boolean equals(Object other)` với phần thân phù hợp. Việc annotation được chấp nhận chỉ xác nhận quan hệ khai báo; nó không chứng minh thuật toán so sánh đúng. Khi thay đổi `equals`, còn phải bảo đảm hợp đồng tương ứng với `hashCode`; đây là phần kiểm tra thiết kế riêng.

### Quên public khi triển khai interface

Nếu interface có `String format(String input)`, phương thức trong lớp triển khai phải là `public String format(String input)`. Thêm `@Override` không làm Java tự nâng quyền truy cập của phương thức.

### Tên hoặc hợp đồng ở kiểu cha đã thay đổi

Khi nâng cấp một thư viện hoặc sửa interface, phương thức từng ghi đè có thể không còn tương ứng. Lỗi xuất hiện tại `@Override` giúp xác định phần triển khai cần cập nhật.

Nếu kiểu con là lớp cụ thể, thiếu triển khai phương thức abstract cũng có thể đã bị trình biên dịch bắt dù không dùng annotation. Giá trị bổ sung của `@Override` đặc biệt rõ khi phương thức cha có sẵn phần thân: một khai báo viết nhầm có thể âm thầm tồn tại như phương thức mới.

### Cho rằng không thấy qua reflection nghĩa là không ghi đè

`@Override` có `SOURCE` retention. Việc không thấy annotation này qua reflection là đúng thiết kế và không nói lên phương thức có quan hệ ghi đè hay không.

Không dùng `method.isAnnotationPresent(Override.class)` làm cách nhận diện các phương thức ghi đè khi chương trình chạy.

## Giới hạn của phép kiểm tra ý định

Biên dịch thành công với `@Override` không chứng minh:

- Giá trị trả về đúng yêu cầu nghiệp vụ.
- Phương thức xử lý đúng `null`, dữ liệu biên hoặc lỗi đầu vào.
- Hợp đồng hành vi của kiểu cha được giữ nguyên.
- Phương thức an toàn luồng hoặc có hiệu năng đạt yêu cầu.
- Các annotation khác trên phương thức cha đã được sao chép sang phương thức con.

Ví dụ, phương thức `convert(String)` trong chương trình không định nghĩa cách xử lý `null`; `@Override` không kiểm tra thay vấn đề đó. Vẫn cần xác định hợp đồng đầu vào và kiểm chứng phần thân phương thức bằng các trường hợp có ý nghĩa.

## Thực hành kiểm chứng

1. Trong `OverrideDemo.java`, đổi `convert(String input)` của lớp con thành `convert(Object input)` và điều chỉnh phần thân cho hợp kiểu. Giữ `@Override`, biên dịch để quan sát việc sai tham số bị phát hiện.
2. Khôi phục chương trình, rồi gắn `@Override` vào `convert(int)`. Biên dịch sẽ thất bại vì trong ví dụ không có phương thức kiểu cha tương ứng.
3. Khôi phục, đổi kiểu trả về của phương thức con từ `String` thành `Object` và giữ phần thân. Chương trình vẫn có quan hệ ghi đè hợp lệ, nhưng mất cam kết kiểu trả về cụ thể hơn cho lời gọi qua kiểu lớp con.
4. Khôi phục, bỏ `@Override` khỏi riêng `convert(String)`. Chạy lại sẽ vẫn in `polymorphism=HELLO`: annotation kiểm tra ý định, không tạo cơ chế đa hình.
5. Đổi tên phương thức ở cả interface và lớp triển khai một cách nhất quán. Sau đó đổi tên ở riêng interface để thấy lỗi biên dịch chỉ ra sự lệch hợp đồng.

Trong mã thực tế, nên viết `@Override` ngay khi có ý định ghi đè hoặc triển khai phương thức, rồi dùng lỗi biên dịch để kiểm tra lại ý định ấy trước khi tiếp tục viết phần thân.
