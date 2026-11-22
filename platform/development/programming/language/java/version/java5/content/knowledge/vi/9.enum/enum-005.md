# Thân lớp riêng của từng hằng enum

## 1. Enum có thể gắn hành vi riêng vào từng hằng

Một enum không chỉ là danh sách tên. Khi mỗi lựa chọn cần thực hiện một hành vi khác nhau nhưng vẫn có cùng giao diện, ta có thể đặt phần triển khai ngay sau từng hằng.

Ví dụ:

```java
enum Mark {
    ROUND {
        @Override
        public String wrap(String value) {
            return "(" + value + ")";
        }
    },
    SQUARE {
        @Override
        public String wrap(String value) {
            return "[" + value + "]";
        }
    };

    public abstract String wrap(String value);
}
```

Đây là enum minh họa có thể đặt trong một tệp Java phù hợp. Ví dụ này chỉ minh họa khác biệt bao dấu, chưa đặt chính sách riêng cho `null`.

Phần `{ }` ngay sau `ROUND` và `SQUARE` được gọi là **thân lớp riêng của hằng (constant-specific class body)**.

Người gọi vẫn sử dụng một kiểu chung:

```java
Mark mark = Mark.SQUARE;
String text = mark.wrap("java");
```

Kết quả là `[java]`. Hành vi được chọn theo đối tượng hằng đang giữ trong `mark`.

Kỹ thuật này vẫn là một phần của Java hiện nay. Nó hữu ích cho một tập lựa chọn đóng, khi từng lựa chọn có hành vi đủ khác nhau để đáng được đặt cạnh chính hằng đó.

## 2. Đọc cấu trúc: đối số constructor, thân riêng và phần chung

Một hằng enum có thể gồm:

1. Tên hằng.
2. Các đối số truyền vào constructor enum.
3. Một thân lớp riêng tùy chọn.

Trong chương trình đầy đủ, ta có dạng:

```java
UPPER("upper") {
    @Override
    protected String transformNonNull(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
```

Đây là một hằng được trích từ khai báo enum; không phải một khai báo lớp độc lập.

- `UPPER` là tên hằng.
- `"upper"` là dữ liệu truyền vào constructor chung.
- Phần `{ }` cài đặt hành vi riêng cho hằng đó.
- Dấu phẩy phân cách các hằng.
- Dấu chấm phẩy sau hằng cuối tách danh sách hằng với các trường và phương thức chung phía sau.

Các thành viên sau danh sách hằng thuộc phần chung của enum: constructor, trường dữ liệu, phương thức thường, phương thức `final` hoặc phương thức `abstract`.

Các quy tắc về hằng enum và thân riêng được định nghĩa ở [JLS: Enum Constants](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.1).

## 3. Hai cách cung cấp hành vi cho các hằng

### 3.1. Khai báo phương thức abstract để mọi hằng phải cài đặt

Nếu hành vi là bắt buộc cho mỗi hằng:

```java
public abstract String wrap(String value);
```

Mỗi hằng phải có phần triển khai cụ thể cho phương thức đó.

Trong enum `Mark`, `ROUND` và `SQUARE` đều cung cấp `wrap`. Nếu thêm một hằng mới mà không có cách triển khai, enum không biên dịch.

Điều này làm yêu cầu “mỗi lựa chọn phải có hành vi” trở thành điều kiện được trình biên dịch kiểm tra.

Không viết thêm từ khóa `abstract` trước khai báo enum. Java cho phép phương thức abstract trong phần chung của enum theo quy tắc riêng, nhưng không cho khai báo `abstract enum`.

### 3.2. Cung cấp hành vi mặc định rồi chỉ ghi đè hằng khác biệt

Nếu đa số hằng có cùng hành vi, có thể cung cấp phương thức cụ thể trong phần chung.

Ví dụ của bài có `DisplayStyle`:

- `PLAIN` không có thân riêng, dùng hành vi chung.
- `BRACKETED` có thân riêng, ghi đè hành vi để thêm dấu ngoặc.

Không bắt buộc mọi hằng đều phải có thân lớp. Có thân hay không phụ thuộc việc hằng đó cần ghi đè hoặc khai báo phần triển khai riêng.

Cần chọn có chủ đích: phương thức abstract làm mọi hằng phải quyết định; phương thức mặc định làm việc không ghi đè trở thành một quyết định hợp lệ.

Quy tắc về phương thức abstract và phần thân enum nằm trong [JLS: Enum Body Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.2).

## 4. Cơ chế phía sau: một lớp con vô danh của enum

Thân riêng của một hằng ngầm khai báo một lớp con vô danh của enum chứa nó.

Có thể hình dung:

```text
TextRule
    |
    +-- lop con vo danh cho TRIM
    |
    +-- lop con vo danh cho UPPER
    |
    +-- lop con vo danh cho BRACKET
```

Đây là hình dung về quan hệ lớp, không phải một cú pháp Java để tự khai báo các lớp con đó.

Các đối tượng vẫn là những hằng enum được đặt tên:

- `TextRule.TRIM` có kiểu mà API công bố là `TextRule`.
- Nó vẫn dùng được ở nơi nhận `TextRule` hoặc interface mà enum thực hiện.
- Nó không tạo thêm hằng nằm ngoài danh sách `values()`.
- Người dùng không được tự `new` một enum hoặc tự tạo lớp con mở rộng enum bên ngoài cơ chế này.

Lời gọi phương thức instance được phân phối theo phần triển khai của đối tượng cụ thể, giống nguyên tắc đa hình thông thường.

Do đó, `rule.apply(...)` có thể đi tới một phương thức chung, rồi phương thức chung gọi một hook được từng hằng ghi đè.

## 5. Chương trình đầy đủ: dùng phần chung để giữ hợp đồng, phần riêng để đổi hành vi

Ta xây `TextRule` với ba lựa chọn:

- `TRIM`: loại khoảng trắng đầu và cuối.
- `UPPER`: chuyển chữ hoa theo `Locale.ROOT`.
- `BRACKET`: thêm dấu ngoặc vuông quanh giá trị.

Hợp đồng chung:

- Có một nhãn dữ liệu cho mỗi hằng.
- Đầu vào khác `null`.
- Kết quả khác `null`.
- Người dùng gọi qua phương thức `apply` chung.
- Mỗi hằng chỉ cài đặt phần biến đổi cụ thể.

Lưu thành `EnumConstantBodyDemo.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class EnumConstantBodyDemo {
    interface TextProcessor {
        String apply(String value);
    }

    enum TextRule implements TextProcessor {
        TRIM("trim") {
            @Override
            protected String transformNonNull(String value) {
                return value.strip();
            }
        },
        UPPER("upper") {
            @Override
            protected String transformNonNull(String value) {
                return value.toUpperCase(Locale.ROOT);
            }
        },
        BRACKET("bracket") {
            @Override
            protected String transformNonNull(String value) {
                return "[" + value + "]";
            }
        };

        private final String label;

        TextRule(String label) {
            this.label = Objects.requireNonNull(label, "label");
        }

        public final String label() {
            return label;
        }

        @Override
        public final String apply(String value) {
            String input = Objects.requireNonNull(value, "value");
            return Objects.requireNonNull(
                    transformNonNull(input), "result");
        }

        protected abstract String transformNonNull(String value);
    }

    enum DisplayStyle {
        PLAIN,
        BRACKETED {
            @Override
            public String decorate(String value) {
                return "[" + Objects.requireNonNull(value, "value") + "]";
            }
        };

        public String decorate(String value) {
            return Objects.requireNonNull(value, "value");
        }
    }

    public static void main(String[] args) {
        String input = " Java ";
        for (TextRule rule : TextRule.values()) {
            System.out.println(rule.name() + "/" + rule.label()
                    + " = \"" + rule.apply(input) + "\"");
        }

        TextProcessor processor = TextRule.UPPER;
        System.out.println("interface call = " + processor.apply("java"));
        System.out.println("valueOf same constant = "
                + (TextRule.valueOf("TRIM") == TextRule.TRIM));
        System.out.println("constant count = " + TextRule.values().length);

        System.out.println("declaring class matches = "
                + (TextRule.TRIM.getDeclaringClass() == TextRule.class));
        System.out.println("runtime class matches = "
                + (TextRule.TRIM.getClass() == TextRule.class));
        System.out.println("constant bodies use different classes = "
                + (TextRule.TRIM.getClass() != TextRule.UPPER.getClass()));
        System.out.println("runtime class is enum = "
                + TextRule.TRIM.getClass().isEnum());
        System.out.println("TextRule is sealed = "
                + TextRule.class.isSealed());

        System.out.println("plain = " + DisplayStyle.PLAIN.decorate("x"));
        System.out.println("bracketed = "
                + DisplayStyle.BRACKETED.decorate("x"));
        System.out.println("plain runtime class matches = "
                + (DisplayStyle.PLAIN.getClass() == DisplayStyle.class));
        System.out.println("bracketed runtime class matches = "
                + (DisplayStyle.BRACKETED.getClass() == DisplayStyle.class));

        try {
            TextRule.TRIM.apply(null);
        } catch (NullPointerException exception) {
            System.out.println("shared null policy rejected input");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror EnumConstantBodyDemo.java
java EnumConstantBodyDemo
```

Stdout:

```text
TRIM/trim = "Java"
UPPER/upper = " JAVA "
BRACKET/bracket = "[ Java ]"
interface call = JAVA
valueOf same constant = true
constant count = 3
declaring class matches = true
runtime class matches = false
constant bodies use different classes = true
runtime class is enum = false
TextRule is sealed = true
plain = x
bracketed = [x]
plain runtime class matches = true
bracketed runtime class matches = false
shared null policy rejected input
```

Dấu nháy kép ở ba dòng đầu giúp nhìn rõ khoảng trắng trong chuỗi. `TRIM` loại khoảng trắng; `UPPER` chỉ đổi chữ, không tự loại khoảng trắng; `BRACKET` giữ nguyên nội dung rồi thêm dấu bao.

Đó là ba hợp đồng hành vi khác nhau, không phải ba giá trị dữ liệu được xử lý bằng cùng một công thức.

## 6. Vì sao apply là final nhưng hành vi vẫn thay đổi theo hằng?

Phần chung khai báo:

```java
@Override
public final String apply(String value) {
    String input = Objects.requireNonNull(value, "value");
    return Objects.requireNonNull(
            transformNonNull(input), "result");
}
```

Đây là phương thức từ enum trong chương trình.

Mọi hằng đều chạy các bước chung:

1. Kiểm tra đầu vào.
2. Gọi phần biến đổi riêng.
3. Kiểm tra kết quả.
4. Trả về chuỗi cho người gọi.

`apply` là `final` nên thân riêng của một hằng không thể thay toàn bộ quy trình để bỏ qua các điều kiện chung.

Điểm được phép thay đổi là:

```java
protected abstract String transformNonNull(String value);
```

Mỗi hằng cài đặt hook này bằng một phương thức instance có cùng chữ ký và mức truy cập phù hợp.

Nhờ vậy, lớp giữ chung trách nhiệm kiểm tra, còn từng hằng giữ trách nhiệm biến đổi. Không cần lặp lại kiểm tra `null` trong cả ba thân riêng.

### Interface là hợp đồng nhìn từ ngoài

`TextRule` thực hiện `TextProcessor`. Biến:

```java
TextProcessor processor = TextRule.UPPER;
```

vẫn gọi được `apply` qua giao diện. Người gọi không cần biết tên lớp con vô danh hoặc cách enum tổ chức hook bên trong.

Không phải mỗi hằng đang thực hiện một interface khác nhau. Enum chung công bố cùng hợp đồng, các thân riêng cung cấp các phần triển khai khác nhau trong giới hạn đó.

## 7. Constructor và trường chung khác thân lớp riêng

### Đối số đi vào constructor của enum

`TRIM("trim")` truyền chuỗi `"trim"` vào constructor `TextRule(String label)`.

Trường:

```java
private final String label;
```

được khai báo trong phần chung. Mỗi hằng có giá trị trường của riêng đối tượng hằng đó.

Nếu khác biệt chỉ là dữ liệu, dùng constructor và một trường `final` thường đã đủ. Không cần tạo thân riêng cho mỗi hằng chỉ để trả một chuỗi nhãn khác nhau.

### Không khai báo constructor trong thân riêng của hằng

Thân riêng mô tả một lớp con vô danh. Nó không có một tên lớp riêng để khai báo constructor theo cách lớp đặt tên thông thường.

Hãy truyền dữ liệu qua đối số của hằng vào constructor enum. Không viết một “constructor UPPER” bên trong khối của hằng để thay thế cơ chế đó.

Constructor enum không được công khai cho người dùng tự tạo thêm đối tượng. Constructor enum không ghi mức truy cập có phạm vi `private`. Không thêm `public` hoặc `protected` để cho phép `new TextRule(...)`.

### Không gọi hook có thể bị ghi đè quá sớm trong constructor

Constructor chung nên thiết lập các trường dữ liệu cần thiết. Nếu nó gọi một phương thức được thân riêng ghi đè trong lúc khởi tạo, phần triển khai riêng có thể chạy trước khi dữ liệu instance riêng của lớp con được khởi tạo đầy đủ.

Ví dụ giữ constructor đơn giản: nhận và kiểm tra nhãn. Quy trình biến đổi chỉ được gọi sau khi hằng đã được khởi tạo.

## 8. getClass khác getDeclaringClass

Đây là một hệ quả thực tế dễ gây nhầm.

Với hằng có thân lớp riêng:

```java
TextRule.TRIM.getClass() == TextRule.class
```

cho `false` trong chương trình. Đối tượng thuộc lớp con vô danh của `TextRule`.

Nhưng:

```java
TextRule.TRIM.getDeclaringClass() == TextRule.class
```

cho `true`. Phương thức này trả kiểu enum mà hằng thuộc về.

Hai hằng `TRIM` và `UPPER` có hai lớp con vô danh khác nhau, nhưng cùng thuộc enum `TextRule`.

Trong `DisplayStyle`:

- `PLAIN` không có thân riêng nên lớp runtime của nó là `DisplayStyle`.
- `BRACKETED` có thân riêng nên lớp runtime là lớp con vô danh.
- Cả hai vẫn là hằng của cùng enum `DisplayStyle`.

### Khi làm việc theo kiểu enum, dùng đúng câu hỏi

Nếu cần biết hằng thuộc enum nào, `getDeclaringClass()` diễn tả đúng yêu cầu hơn so sánh `getClass()`.

`getClass().isEnum()` trên lớp con vô danh của hằng có thể là `false`. Điều đó không có nghĩa đối tượng không còn là một hằng enum.

Không dùng tên do trình biên dịch sinh cho lớp con vô danh làm mã định danh lưu trữ hoặc giao thức. Tên đó là chi tiết triển khai; chương trình cố ý chỉ kiểm tra quan hệ lớp, không in hoặc phụ thuộc các hậu tố tên lớp.

Hợp đồng của phương thức được nêu trong [Enum.getDeclaringClass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()).

## 9. Trong Java hiện hành, enum không phải luôn ngầm final theo cùng một cách

Quy tắc hiện hành:

- Enum không có hằng nào mang thân lớp riêng là enum ngầm `final`.
- Enum có ít nhất một hằng mang thân lớp riêng là enum ngầm `sealed`.
- Các lớp con trực tiếp được phép là các lớp vô danh được những hằng đó khai báo ngầm.

Vì vậy, `TextRule.class.isSealed()` là `true` trong chương trình chạy với mức ngôn ngữ Java 17.

Điều này không mở quyền cho người dùng tự viết một lớp mở rộng `TextRule`. Danh sách lớp con thuộc cơ chế hằng enum vẫn được ngôn ngữ kiểm soát.

Cũng không viết thêm các từ khóa `sealed`, `final`, `abstract` hoặc `non-sealed` trực tiếp vào khai báo enum. Những trạng thái liên quan của enum được xác định ngầm theo các quy tắc dành riêng cho enum.

Quy tắc được mô tả tại [JLS: Enum Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9). Không dùng một lời giải thích đơn giản rằng “mọi enum đều final nên không thể có lớp con” để phủ nhận cơ chế thân riêng của hằng.

## 10. Phương thức mới chỉ nằm trong thân riêng không tự thành API chung

Có thể khai báo một helper riêng bên trong thân hằng để phần triển khai của hằng sử dụng. Nhưng nếu một phương thức chỉ có ở lớp con vô danh, nó không tự xuất hiện trên kiểu enum mà người gọi đang giữ.

Ví dụ cố ý không biên dịch tại lời gọi `detail`:

```java
enum DetailMode {
    ONLY {
        public String detail() {
            return "only";
        }
    };
}

// DetailMode.ONLY.detail(); // Khong bien dich
```

Hằng `ONLY` được công bố với kiểu `DetailMode`. Kiểu đó không khai báo `detail()`.

Nếu người dùng cần gọi hành vi đó như một phần API, hãy khai báo phương thức phù hợp ở phần chung hoặc interface, rồi để hằng ghi đè.

Không dùng reflection hoặc ép sang một lớp do compiler sinh để biến một phương thức hằng riêng thành giao thức công khai. Khi nhu cầu là API chung, hãy đặt nó vào hợp đồng chung.

### @Override giúp phát hiện sai chữ ký

Nếu gõ nhầm tên, đổi kiểu tham số hoặc vô tình tạo overload, phương thức mới có thể không ghi đè điều mong muốn.

Dùng `@Override` trên các phương thức thân riêng khiến compiler xác nhận quan hệ ghi đè. Nó cũng giúp tránh việc enum abstract vẫn chưa được cài đặt dù trông như đã có một phương thức tương tự.

Các phương thức `final` không thể được ghi đè. Ngoài `apply` final do ví dụ tự định nghĩa, nhiều hành vi định danh của `Enum` như `name()` và `equals` cũng không phải điểm tùy biến cho từng hằng.

## 11. Chọn thân riêng hay dữ liệu constructor hay switch?

| Dạng khác biệt | Cách biểu diễn thường phù hợp |
| --- | --- |
| Chỉ khác nhãn, mã hoặc một hệ số dùng cùng công thức | Trường `final` và constructor |
| Mỗi hằng có một thuật toán instance khác nhau thuộc trách nhiệm enum | Thân riêng và phương thức chung |
| Phần lớn dùng hành vi chung, một số khác biệt | Phương thức cụ thể mặc định và override có chọn lọc |
| Mọi hằng phải tự quyết định hành vi | Phương thức abstract chung |
| Một tác vụ bên ngoài phân loại các hằng, không thuộc trách nhiệm enum | Có thể dùng switch tại tác vụ đó |
| Tập hành vi phải được mở rộng động bởi bên ngoài | Cân nhắc interface và các cách cài đặt riêng |

Không coi mọi `switch` trên enum là lỗi thiết kế. Một phép chiếu phục vụ màn hình hoặc một thao tác cục bộ bên ngoài enum có thể thuộc trách nhiệm của nơi khác.

Ngược lại, nếu nhiều nơi lặp lại cùng một `switch` để thực hiện cùng hành vi cốt lõi của từng hằng, đặt hành vi vào enum có thể làm quan hệ rõ hơn.

Một phương thức abstract yêu cầu mỗi hằng có phần triển khai. Một switch expression đầy đủ cũng có thể được compiler kiểm tra theo các quy tắc của nó. Đừng so sánh bằng một khẳng định rằng chỉ một hình thức mới có khả năng kiểm tra tại lúc biên dịch.

## 12. Trạng thái trong thân riêng cần được cân nhắc

Một hằng enum là một đối tượng được dùng lại. Thêm một trường có thể thay đổi trong thân riêng không tạo ra một bản trạng thái mới cho mỗi lần gọi.

Ví dụ, nếu một hằng giữ bộ đếm hoặc bộ đệm mutable, những lần gọi khác nhau có thể cùng quan sát trạng thái đó. Việc hằng enum được công bố bằng tham chiếu ổn định không làm mọi trường bên trong tự trở nên bất biến.

Ví dụ của bài dùng:

- Nhãn `final`.
- Đầu vào và kết quả là `String`.
- Biến cục bộ cho quá trình xử lý.
- Không có trạng thái mutable được giữ giữa các lời gọi.

Nếu thuật toán cần trạng thái theo từng yêu cầu, thường nên truyền trạng thái đó vào hoặc tạo một đối tượng xử lý riêng. Chỉ giữ nó trong hằng khi sự chia sẻ và vòng đời đó thật sự thuộc hợp đồng.

Không đưa một hệ thống phụ thuộc phức tạp vào các thân enum chỉ vì cú pháp cho phép. Tập hằng cố định và vòng đời đối tượng enum có thể không phù hợp với hành vi cần cấu hình hoặc thay thế linh hoạt.

## 13. Những lỗi cần nhận ra

| Lỗi | Kết quả hoặc hiểu nhầm | Cách sửa |
| --- | --- | --- |
| Thêm hằng mà quên cài đặt phương thức abstract | Không biên dịch | Cung cấp phần triển khai hoặc chọn hành vi chung phù hợp |
| Quên dấu chấm phẩy trước phần thành viên chung | Lỗi cú pháp | Tách danh sách hằng với phần khai báo chung |
| Ghi đè sai chữ ký | Không thực hiện đúng hợp đồng | Dùng `@Override` |
| Cố ghi đè phương thức final | Không biên dịch | Chọn một hook được thiết kế để thay đổi |
| Chỉ khai báo phương thức public trong một thân hằng rồi gọi qua kiểu enum | Không có phương thức trên API enum | Khai báo hợp đồng ở phần chung |
| Dùng getClass để xác định enum chứa hằng | Sai với hằng có thân riêng | Dùng `getDeclaringClass` khi đó là yêu cầu |
| Tự viết constructor trong thân hằng | Không đúng mô hình lớp vô danh | Dùng constructor enum và đối số hằng |
| Mặc định các trường mutable là trạng thái riêng của từng lần gọi | Chia sẻ trạng thái ngoài ý muốn | Thiết kế vòng đời trạng thái rõ ràng |

Các lớp con vô danh không thay đổi cách lấy các hằng bằng `values()` hoặc `valueOf`. Ví dụ vẫn có ba hằng, và `valueOf("TRIM")` trả đúng hằng `TRIM` đã có.

## 14. Thực hành tự kiểm tra

### Bài 1: Có bắt buộc mọi hằng có thân riêng không?

**Đáp án:** không nếu chúng có thể dùng phương thức cụ thể trong phần chung. Nhưng nếu enum có phương thức abstract cần được cung cấp cho từng hằng, mọi hằng phải có phần triển khai cụ thể theo quy tắc enum.

### Bài 2: Chỉ khác nhãn

Ba hằng chỉ khác một chuỗi nhãn, còn cùng công thức xử lý. Có nhất thiết viết ba thân lớp riêng không?

**Đáp án:** không. Truyền nhãn vào constructor và dùng một phương thức chung thường rõ hơn.

### Bài 3: final apply vẫn có hành vi khác

Vì sao `apply` là final nhưng `UPPER` và `TRIM` vẫn xử lý khác nhau?

**Đáp án:** `apply` giữ các bước chung và gọi hook `transformNonNull`. Mỗi hằng ghi đè hook, không ghi đè toàn bộ quy trình.

### Bài 4: Lớp runtime

`TextRule.TRIM.getClass()` khác `TextRule.class` có nghĩa TRIM không thuộc enum TextRule không?

**Đáp án:** không. Nó thuộc lớp con vô danh được hằng khai báo ngầm; `getDeclaringClass()` vẫn trả `TextRule.class`.

### Bài 5: Phương thức chỉ ở một hằng

Vì sao một `detail()` chỉ khai báo trong thân hằng không tự gọi được bằng `EnumType.CONSTANT.detail()`?

**Đáp án:** trường hằng được công bố theo kiểu enum chung. Nếu hành vi phải được gọi từ ngoài, phương thức cần nằm trong hợp đồng chung và được ghi đè phù hợp.

### Bài 6: Hằng mới và hành vi abstract

Điều gì xảy ra nếu thêm hằng mới nhưng không cài đặt hook abstract?

**Đáp án:** compiler từ chối enum, thay vì để người dùng có một hằng không có hành vi bắt buộc khi chạy.

Thân lớp riêng cho phép đặt phần triển khai khác biệt cạnh từng hằng, trong khi kiểu enum vẫn giữ giao diện và quy tắc chung. Hãy dùng nó khi khác biệt thật sự là hành vi của từng lựa chọn, đồng thời giữ rõ ranh giới giữa dữ liệu constructor, hợp đồng chung và phần được phép ghi đè.
