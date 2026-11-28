# Tái cấu trúc chuỗi kiểm tra kiểu mà giữ thứ tự và hành vi

## 1. Mục tiêu của việc tái cấu trúc

Trong mã Java, một chuỗi `if` / `else if` thường kiểm tra cùng một giá trị để quyết định cách xử lý theo kiểu thực tế của đối tượng. Trước Java 16, mỗi nhánh thường lặp lại kiểu cần kiểm tra và phép ép kiểu:

~~~java
if (value instanceof Invoice) {
    Invoice invoice = (Invoice) value;
    return "Hóa đơn: " + invoice.title();
} else if (value instanceof Document) {
    Document document = (Document) value;
    return "Tài liệu: " + document.title();
} else if (value instanceof CharSequence) {
    CharSequence text = (CharSequence) value;
    return "Văn bản: " + text;
}
~~~

Từ Java 16, pattern matching for `instanceof` cho phép gộp phép kiểm tra kiểu với khai báo biến:

~~~java
if (value instanceof Invoice invoice) {
    return "Hóa đơn: " + invoice.title();
} else if (value instanceof Document document) {
    return "Tài liệu: " + document.title();
} else if (value instanceof CharSequence text) {
    return "Văn bản: " + text;
}
~~~

Việc tái cấu trúc có vẻ đơn giản, nhưng cần giữ nguyên những quyết định vốn có của chuỗi điều kiện:

- Nhánh nào được kiểm tra trước.
- Nhánh nào được chọn khi một đối tượng khớp nhiều kiểu.
- Điều kiện phụ và thứ tự đánh giá của chúng.
- Giá trị trả về, ngoại lệ và tác dụng phụ của từng nhánh.
- Cách xử lý `null` và trường hợp không khớp.

Type pattern giúp loại bỏ ép kiểu lặp lại. Nó không tự quyết định thứ tự nghiệp vụ của các nhánh.

## 2. Giữ nguyên thứ tự từ kiểu cụ thể đến kiểu tổng quát

Một lớp con cũng là instance của lớp cha. Vì vậy, khi các nhánh có quan hệ kế thừa, thứ tự kiểm tra ảnh hưởng trực tiếp đến kết quả.

Ví dụ, `Invoice` kế thừa `Document`:

~~~java
public class DocumentFormatter {
    static class Document {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        String title() {
            return title;
        }
    }

    static final class Invoice extends Document {
        private final long totalCents;

        Invoice(String title, long totalCents) {
            super(title);
            this.totalCents = totalCents;
        }

        long totalCents() {
            return totalCents;
        }
    }

    static final class Note extends Document {
        Note(String title) {
            super(title);
        }
    }

    static String describe(Object value) {
        if (value instanceof Invoice invoice) {
            return "Hóa đơn: " + invoice.title()
                    + ", tổng tiền: " + invoice.totalCents();
        } else if (value instanceof Document document) {
            return "Tài liệu: " + document.title();
        } else if (value instanceof CharSequence text) {
            return "Văn bản: " + text;
        } else if (value == null) {
            return "Không có dữ liệu";
        } else {
            return "Kiểu khác: " + value.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        Object[] values = {
                new Invoice("INV-100", 250_000),
                new Note("Ghi chú nội bộ"),
                "Văn bản tự do",
                42,
                null
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }
    }
}
~~~

Nhánh `Invoice` phải đứng trước `Document`. Một `Invoice` cũng là một `Document`, nên nếu kiểm tra `Document` trước, nhánh tổng quát sẽ nhận đối tượng và nhánh `Invoice` phía sau không còn cơ hội chạy.

Kết quả của ví dụ:

~~~text
Hóa đơn: INV-100, tổng tiền: 250000
Tài liệu: Ghi chú nội bộ
Văn bản: Văn bản tự do
Kiểu khác: Integer
Không có dữ liệu
~~~

Khi chuyển một chuỗi kiểm tra cũ sang type pattern, hãy giữ nguyên thứ tự các nhánh trước tiên. Chỉ thay phần kiểm tra và ép kiểu; đừng đổi vị trí các nhánh cùng lúc nếu chưa xác nhận đó là thay đổi nghiệp vụ mong muốn.

## 3. `else if` có ý nghĩa khác với nhiều câu `if` độc lập

Một đối tượng có thể triển khai nhiều interface cùng lúc. Trong chuỗi `if` / `else if`, chỉ nhánh đầu tiên đúng được thực hiện:

~~~java
interface Printable {
    void print();
}

interface Auditable {
    void audit();
}

class Report implements Printable, Auditable {
    @Override
    public void print() {
        System.out.println("In báo cáo");
    }

    @Override
    public void audit() {
        System.out.println("Ghi nhật ký kiểm tra");
    }
}

class ReportDispatcher {
    static void handle(Object value) {
        if (value instanceof Printable printable) {
            printable.print();
        } else if (value instanceof Auditable auditable) {
            auditable.audit();
        }
    }
}
~~~

`Report` triển khai cả `Printable` và `Auditable`, nhưng `handle` chỉ gọi `print()` vì nhánh đầu tiên đã khớp. Nếu thay `else if` bằng một câu `if` độc lập, cả hai hành vi đều được thực hiện:

~~~java
if (value instanceof Printable printable) {
    printable.print();
}
if (value instanceof Auditable auditable) {
    auditable.audit();
}
~~~

Đây là thay đổi hành vi, không chỉ là thay đổi cách trình bày. Khi tái cấu trúc, giữ `else if` nếu mục đích ban đầu là chọn đúng một nhánh. Chỉ dùng các câu `if` độc lập khi nghiệp vụ thật sự yêu cầu mọi hành vi phù hợp đều được chạy.

## 4. Giữ điều kiện phụ và thứ tự đánh giá

Pattern variable có thể dùng ngay trong vế phải của `&&`, vì vế phải chỉ được đánh giá sau khi pattern khớp:

~~~java
class TextFormatter {
    static String format(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi có nội dung: " + text.strip();
        } else if (value instanceof CharSequence sequence) {
            return "Dữ liệu dạng văn bản: " + sequence.length();
        }
        return "Không phải văn bản";
    }
}
~~~

Thứ tự này có chủ đích:

- Chuỗi không rỗng đi vào nhánh `String`.
- Chuỗi rỗng hoặc chỉ có khoảng trắng không vượt qua điều kiện phụ, nhưng vẫn có thể khớp `CharSequence` ở nhánh kế tiếp.
- Giá trị `null` không khớp cả hai pattern và đi đến kết quả mặc định.

Không nên chuyển điều kiện phụ sang vị trí làm thay đổi nhánh được chọn. Ví dụ, nếu bỏ điều kiện `!text.isBlank()`, chuỗi trắng sẽ được xử lý như chuỗi có nội dung. Nếu đổi thứ tự hai nhánh, `String` sẽ bị nhận bởi nhánh `CharSequence` trước.

Với điều kiện phức tạp, nên giữ nguyên toán tử và thứ tự ngắn mạch. `&&` dừng khi vế trái sai; `||` dừng khi vế trái đúng. Các quy tắc này có thể quyết định một phương thức có được gọi hay không và pattern variable có được phép dùng ở vị trí đó hay không.

## 5. Có thể thay ép kiểu bằng guard clause mà vẫn giữ ý nghĩa

Một chuỗi `else if` đôi khi có thể được viết thành các guard clause khi mỗi nhánh kết thúc bằng `return` hoặc `throw`:

~~~java
class ValueFormatter {
    static String format(Object value) {
        if (value instanceof String text) {
            return text.strip();
        }

        if (value instanceof Number number) {
            return number.toString();
        }

        if (value == null) {
            return "(trống)";
        }

        return value.getClass().getSimpleName();
    }
}
~~~

Ở đây các câu `if` độc lập vẫn chỉ thực hiện một nhánh vì mỗi nhánh khớp đều kết thúc phương thức. Cách viết này có thể làm luồng xử lý dễ theo dõi hơn.

Điều kiện để chuyển an toàn là nhánh trước phải kết thúc đường đi hiện tại. Nếu nhánh trước chỉ ghi log hoặc cập nhật trạng thái rồi tiếp tục, thay `else if` bằng `if` độc lập có thể khiến các nhánh sau cũng chạy. Hãy kiểm tra `return`, `throw`, `break`, `continue` và mọi đường đi còn tiếp tục trước khi đổi cấu trúc.

## 6. Giữ nguyên xử lý `null` và nhánh mặc định

`instanceof` trả về `false` khi biểu thức nguồn là `null`, kể cả khi dùng type pattern. Vì vậy, một chuỗi kiểm tra kiểu có thể để `null` rơi xuống nhánh mặc định:

~~~java
class DefaultValueFormatter {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "Chuỗi: " + text;
        } else if (value instanceof Number number) {
            return "Số: " + number;
        } else {
            return "Giá trị khác";
        }
    }
}
~~~

Trong ví dụ này, `null` trả về `"Giá trị khác"`. Nếu phiên bản cũ xử lý `null` theo cách riêng, phải giữ nhánh đó:

~~~java
class ExplicitNullFormatter {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "Chuỗi: " + text;
        } else if (value == null) {
            return "Không có dữ liệu";
        } else if (value instanceof Number number) {
            return "Số: " + number;
        } else {
            return "Giá trị khác";
        }
    }
}
~~~

Di chuyển nhánh `null` có thể an toàn trong một số chuỗi điều kiện vì các pattern không khớp với `null`, nhưng vẫn cần giữ nguyên thứ tự nếu nhánh có thêm điều kiện, log hoặc tác dụng phụ. Cách rõ ràng nhất là xác định trước kết quả mong đợi cho `null`, sai kiểu và kiểu hợp lệ.

## 7. Tránh thay đổi số lần đánh giá biểu thức nguồn

Nếu biểu thức nguồn là biến cục bộ ổn định, dùng lại biến đó trong các nhánh là tự nhiên. Nếu biểu thức là lời gọi phương thức, việc lặp lại lời gọi có thể tạo ra tác dụng phụ hoặc trả về kết quả khác nhau:

~~~java
class ValueSource {
    private int nextId;

    Object next() {
        nextId++;
        return nextId % 2 == 1 ? Integer.valueOf(nextId) : "Java";
    }
}
~~~

Ví dụ, chuỗi điều kiện gọi `source.next()` riêng ở từng nhánh:

~~~java
class RepeatedSourceEvaluation {
    static void check(ValueSource source) {
        if (source.next() instanceof String text) {
            System.out.println(text);
        } else if (source.next() instanceof Number number) {
            System.out.println(number);
        }
    }
}
~~~

Hai nhánh có thể kiểm tra hai đối tượng khác nhau vì `next()` được gọi lại khi nhánh đầu không khớp. Với `ValueSource` trên, lần gọi đầu trả về `Integer`, lần gọi thứ hai trả về `String`; do đó nhánh kiểm tra `Number` nhận một giá trị khác với giá trị đã kiểm tra ở nhánh đầu. Nếu đổi thành:

~~~java
class SingleSourceEvaluation {
    static void check(ValueSource source) {
        Object candidate = source.next();

        if (candidate instanceof String text) {
            System.out.println(text);
        } else if (candidate instanceof Number number) {
            System.out.println(number);
        }
    }
}
~~~

thì chỉ một đối tượng được lấy và mọi nhánh kiểm tra cùng đối tượng đó. Đây thường là thiết kế mong muốn khi xử lý một giá trị đầu vào, nhưng nó không tương đương với mã cũ nếu `next()` có tác dụng phụ hoặc kết quả thay đổi theo lần gọi.

Khi tái cấu trúc, xác định rõ biểu thức nguồn có cần được đánh giá một lần hay nhiều lần. Nếu muốn giữ hành vi cũ, không tự ý thay đổi số lần gọi. Nếu muốn sửa lỗi do gọi lặp, hãy xem đó là một thay đổi hành vi riêng và kiểm tra lại yêu cầu của chương trình.

## 8. Checklist giữ nguyên hành vi khi refactor

Trước khi hoàn tất, so sánh chuỗi cũ và chuỗi mới theo từng điểm:

| Điểm cần kiểm tra | Câu hỏi |
| --- | --- |
| Thứ tự nhánh | Kiểu con có còn được kiểm tra trước kiểu cha không? |
| Quan hệ interface | Đối tượng triển khai nhiều interface có còn đi vào đúng nhánh đầu tiên không? |
| Cấu trúc điều kiện | `else if` có bị đổi thành `if` độc lập không? |
| Điều kiện phụ | Các điều kiện `&&`/`||` có giữ nguyên vị trí và thứ tự không? |
| Giá trị trả về | Mỗi nhánh còn trả về cùng giá trị như trước không? |
| Ngoại lệ | Điều kiện hoặc thao tác nào có thể ném ngoại lệ đã bị chuyển vị trí không? |
| Tác dụng phụ | Các lời gọi phương thức, ghi log hoặc cập nhật trạng thái có đổi số lần chạy không? |
| `null` và fallback | `null`, kiểu không hỗ trợ và nhánh mặc định có giữ kết quả cũ không? |
| Pattern variable | Mỗi biến chỉ được dùng trong phạm vi mà pattern đã khớp không? |

Một cách thực tế là lập bảng đầu vào đại diện trước khi sửa: một instance của từng subtype, một instance chỉ thuộc kiểu cha, đối tượng triển khai nhiều interface, `null` và một kiểu không được hỗ trợ. So sánh kết quả hoặc tác dụng phụ trước và sau khi thay đổi.

## 9. Phạm vi cú pháp Java 16

Trong bài này, cú pháp mới được sử dụng là type pattern của `instanceof`:

~~~java
class InvoiceReader {
    static final class Invoice {
        long totalCents() {
            return 250_000;
        }
    }

    static void print(Object value) {
        if (value instanceof Invoice invoice) {
            System.out.println(invoice.totalCents());
        }
    }
}
~~~

Biến `invoice` đại diện cho toàn bộ đối tượng `Invoice`. Nếu cần dữ liệu bên trong, gọi phương thức hoặc accessor thông thường của kiểu đó.

Khi viết mã tương thích Java 16, không cần chuyển chuỗi kiểm tra kiểu thành cú pháp pattern `switch` hoặc record pattern của các phiên bản Java sau. Chuỗi `if` / `else if` với type pattern đã giải quyết được việc bỏ ép kiểu thủ công mà vẫn giữ thứ tự và hành vi của chương trình.

**Ghi nhớ:** Refactor chuỗi `instanceof` an toàn là thay phần kiểm tra và ép kiểu bằng type pattern, đồng thời giữ nguyên thứ tự nhánh, cấu trúc `else if`, điều kiện phụ, giá trị trả về, tác dụng phụ và xử lý `null`. Đặc biệt, hãy kiểm tra các subtype và interface có thể cùng khớp trước khi đổi thứ tự hoặc tách nhánh.
