# Đọc Javadoc về yêu cầu triển khai, phương thức tùy chọn và default method

Javadoc của một API Java mô tả cách gọi API và những điều mà người triển khai phải bảo đảm. Khi đọc interface trong JDK, đừng chỉ nhìn chữ ký phương thức: cần biết phương thức nào bắt buộc phải triển khai, phương thức nào là tùy chọn, implementation mặc định làm gì, và điều kiện nào khiến lời gọi ném exception.

Ba khái niệm liên quan nhưng không đồng nghĩa:

- **Yêu cầu triển khai** (*implementation requirements/specification*) mô tả điều mà implementation phải làm hoặc phải giữ đúng.
- **Phương thức tùy chọn** (*optional operation*) là thao tác mà một implementation được phép không hỗ trợ theo hợp đồng API. Khi không hỗ trợ, API thường quy định ném `UnsupportedOperationException`.
- **Default method** là phương thức instance trong interface có phần thân mặc định. Lớp triển khai có thể kế thừa hành vi đó hoặc override nó.

Một phương thức có thể vừa là default method vừa là optional operation, nhưng hai khái niệm này độc lập: có default method không tự động có nghĩa là thao tác tùy chọn.

## 1. Đọc Javadoc theo thứ tự nào?

Khi gặp một kiểu hoặc phương thức trong JDK, hãy đọc các phần sau:

1. **Mô tả ngắn và mô tả đầy đủ:** phương thức giải quyết vấn đề gì, có side effect hay không, và hợp đồng chung là gì.
2. **Chữ ký và modifier:** phương thức là abstract, default, static hay phương thức của class; kiểu trả về, tham số và generic type là gì.
3. **`@param` và `@return`:** đầu vào có được phép `null` không, giá trị trả về có thể là `null` không, kết quả có phải bản sao hay view không, và trạng thái nào được bảo đảm.
4. **`@throws`:** exception được ném trong điều kiện nào. Cần phân biệt điều kiện lỗi đầu vào với exception báo rằng implementation không hỗ trợ thao tác.
5. **Implementation Requirements / `@implSpec`:** hợp đồng hoặc yêu cầu dành cho người viết implementation, đặc biệt khi API cung cấp default method.
6. **Implementation Note / `@implNote`:** thông tin về cách implementation cụ thể được xây dựng. Không mặc nhiên xem chi tiết này là bảo đảm cho mọi implementation.
7. **API Note / `@apiNote`:** ngữ cảnh và lời khuyên sử dụng giúp người gọi hiểu cách dùng API.
8. **`@since`, `@see` và liên kết kế thừa:** phiên bản API xuất hiện, các phương thức liên quan và hợp đồng được kế thừa từ interface hoặc superclass.

Chữ ký cho biết mã có thể gọi gì; Javadoc cho biết lời gọi có ý nghĩa gì và những bảo đảm nào được phép dựa vào. Khi hợp đồng ghi rõ điều kiện hỗ trợ, mutability, thứ tự, tính nhất quán hoặc exception, hãy dựa vào hợp đồng đó thay vì đoán từ tên phương thức.

## 2. `@implSpec`, `@implNote` và `@apiNote`

Các block tag này giúp tách biệt những loại thông tin khác nhau trong Javadoc:

| Tag | Dùng để đọc điều gì? | Cách áp dụng |
| --- | --- | --- |
| `@implSpec` | Yêu cầu hoặc hợp đồng mà implementation phải tuân thủ; thường được hiển thị thành phần **Implementation Requirements**. | Dùng khi triển khai hoặc override API; không được vi phạm hành vi đã quy định. |
| `@implNote` | Ghi chú về chi tiết triển khai cụ thể, chẳng hạn cách một implementation thực hiện công việc. | Dùng để hiểu implementation đó; tránh giả định chi tiết là đặc tính chung của interface. |
| `@apiNote` | Ghi chú hữu ích cho người dùng API, ví dụ cách sử dụng hoặc bối cảnh thiết kế. | Dùng để hiểu cách gọi API đúng mục đích. |

Ví dụ Javadoc cho một default method có thể ghi:

```java
/**
 * Removes all entries.
 *
 * @implSpec The default implementation throws
 *           UnsupportedOperationException.
 * @throws UnsupportedOperationException if clearing is not supported
 */
default void clear() {
    throw new UnsupportedOperationException("clear");
}
```

`@implSpec` giải thích hành vi mặc định mà người triển khai cần hiểu khi kế thừa hoặc override phương thức. `@throws` mô tả điều kiện exception. Nếu một implementation override `clear()`, người viết cần đọc toàn bộ hợp đồng để không vô tình phá vỡ điều mà caller được phép trông đợi.

Đừng hiểu `@implNote` như một cam kết chung. Chẳng hạn, ghi chú “implementation này lưu phần tử trong `ArrayList`” không cho phép caller phụ thuộc vào `ArrayList` nếu kiểu API không công bố điều đó.

## 3. Phương thức bắt buộc và phương thức tùy chọn

### Phương thức bắt buộc triển khai

Phương thức abstract trong interface chỉ khai báo hợp đồng, không có phần thân mặc định. Một class concrete triển khai interface phải cung cấp implementation cho các abstract method mà nó chưa thừa hưởng implementation hợp lệ; nếu chưa làm được, class phải được khai báo `abstract`.

Ví dụ:

```java
interface Encoder {
    byte[] encode(String value);
}
```

Class concrete thực hiện `Encoder` phải định nghĩa `encode(String)`, trừ khi phương thức đã được thừa hưởng từ một superclass theo cách hợp lệ. Javadoc của `encode` vẫn cần được đọc để biết cách xử lý `null`, charset, lỗi và ý nghĩa của mảng byte trả về.

### Phương thức tùy chọn

Javadoc gọi một thao tác là **optional operation** khi implementation được phép không hỗ trợ thao tác đó. Caller không thể suy ra rằng mọi object thuộc cùng interface đều hỗ trợ mọi operation chỉ từ việc phương thức xuất hiện trong API.

Một ví dụ JDK là `Collection.add(E)`: tài liệu API mô tả đây là optional operation và quy định `UnsupportedOperationException` nếu collection không hỗ trợ thêm phần tử. Một collection không sửa đổi được có thể cho phép đọc nhưng từ chối thao tác thay đổi. Caller cần biết collection đang dùng có hỗ trợ thao tác cần thiết hay không, hoặc xử lý exception theo hợp đồng phù hợp.

Điểm cần nhớ:

- “Optional” mô tả khả năng hỗ trợ thao tác theo hợp đồng API, không có nghĩa caller được phép bỏ qua mọi quy tắc của phương thức.
- Một optional operation có thể được khai báo là abstract; implementation vẫn phải cung cấp một method body nhưng có thể báo không hỗ trợ bằng exception theo hợp đồng.
- Một API cũng có thể dùng default method ném `UnsupportedOperationException` làm hành vi mặc định cho thao tác tùy chọn.
- Không phải mọi `UnsupportedOperationException` đều chứng minh thao tác là optional trong toàn bộ API; hãy đọc Javadoc của đúng phương thức và kiểu cụ thể.

### `UnsupportedOperationException` khác với lỗi đầu vào

`IllegalArgumentException` thường báo đối số không hợp lệ theo hợp đồng. `UnsupportedOperationException` thường báo object hoặc implementation không hỗ trợ thao tác được yêu cầu. Hai exception có ý nghĩa khác nhau; không nên dùng chúng thay thế tùy tiện hoặc bắt tất cả exception rồi giả vờ thao tác thành công.

## 4. Default method hoạt động ra sao?

Từ Java 8, interface có thể khai báo phương thức instance với từ khóa `default` và cung cấp phần thân:

```java
interface Named {
    String name();

    default String displayName() {
        return "[" + name() + "]";
    }
}
```

Class triển khai `Named` phải cung cấp `name()` nếu chưa có implementation hợp lệ được thừa hưởng. Nó có thể dùng trực tiếp `displayName()` hoặc override phương thức đó. Default method giúp interface bổ sung hành vi chung mà không bắt mỗi class phải viết lại cùng một phần thân.

Default method vẫn là phương thức instance: nó được gọi trên object và có thể gọi các phương thức khác trong hợp đồng. Phần thân mặc định không tự bảo đảm rằng mọi thao tác mà nó gọi đều được implementation hỗ trợ; người đọc vẫn phải kiểm tra Javadoc và các điều kiện của phương thức được gọi.

### Quy tắc chọn implementation

Khi cùng một chữ ký xuất hiện ở class và các interface, hãy nhớ những nguyên tắc chính:

1. **Implementation của class ưu tiên hơn default method của interface.** Nếu class hoặc superclass có phương thức instance phù hợp, nó được ưu tiên theo quy tắc của Java.
2. **Interface cụ thể hơn có thể ưu tiên interface cha.** Nếu một interface con override default method của interface cha, implementation kế thừa qua interface con được ưu tiên.
3. **Hai default method xung đột từ các interface không có quan hệ cụ thể hơn** có thể buộc class phải override và chọn hành vi rõ ràng; nếu không giải quyết được xung đột, mã sẽ không biên dịch.
4. **Default method không thay thế abstract method bằng tên gọi chung chung.** Chỉ phương thức có phần thân `default` mới cung cấp implementation mặc định; static method của interface không được kế thừa như một instance method.

Ví dụ xung đột:

```java
interface A {
    default String label() { return "A"; }
}
interface B {
    default String label() { return "B"; }
}

class Combined implements A, B {
    @Override
    public String label() {
        return A.super.label();
    }
}
```

`Combined` phải xử lý xung đột bằng override; trong ví dụ, nó chủ động chọn phần thân từ `A`. Cú pháp `A.super.label()` chỉ dùng được khi quan hệ interface và method cho phép gọi trực tiếp như vậy.

## 5. Default method và optional operation không phải một khái niệm

Có thể phân biệt bằng hai câu hỏi:

- **Default method:** “Nếu class không override, Java dùng phần thân nào?”
- **Optional operation:** “Theo hợp đồng, implementation có được phép không hỗ trợ thao tác này không?”

Có bốn tình huống cần phân biệt:

| Trường hợp | Ý nghĩa |
| --- | --- |
| Abstract method, bắt buộc có hành vi | Class concrete phải cung cấp implementation và đáp ứng hợp đồng. |
| Abstract method, optional operation | Class concrete vẫn cung cấp method body, nhưng hợp đồng cho phép báo không hỗ trợ bằng cách đã quy định. |
| Default method, hành vi mặc định thông thường | Class có thể kế thừa hành vi và phải giữ đúng hợp đồng khi override. |
| Default method, optional operation | Hành vi mặc định có thể ném `UnsupportedOperationException`; class hỗ trợ thao tác có thể override. |

JDK `Collection.add(E)` là ví dụ hữu ích cho optional operation; `Iterator.remove()` minh họa một optional operation có default implementation ném `UnsupportedOperationException`. Khi đọc tài liệu, hãy tìm cả tuyên bố “optional operation” lẫn phần `@implSpec`/`@throws`, thay vì suy luận từ chữ `default` trong chữ ký.

## 6. Ví dụ Java 17+: implementation kế thừa và override thao tác tùy chọn

Ví dụ này tạo một interface có phương thức `clear()` mặc định ném `UnsupportedOperationException`. `AppendOnlyLog` kế thừa hành vi đó; `EditableLog` override `clear()` để hỗ trợ xóa. Javadoc mô tả rõ rằng thao tác là tùy chọn.

Lưu mã đầy đủ vào `JavadocContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class JavadocContractDemo {
    interface MessageLog {
        void append(String message);
        int size();

        /**
         * Removes all messages from this log.
         * This is an optional operation.
         *
         * @implSpec The default implementation throws
         *           UnsupportedOperationException.
         * @throws UnsupportedOperationException if clearing is not supported
         */
        default void clear() {
            throw new UnsupportedOperationException("clear");
        }
    }

    static final class AppendOnlyLog implements MessageLog {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void append(String message) {
            messages.add(message);
        }

        @Override
        public int size() {
            return messages.size();
        }
    }

    static final class EditableLog implements MessageLog {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void append(String message) {
            messages.add(message);
        }

        @Override
        public int size() {
            return messages.size();
        }

        @Override
        public void clear() {
            messages.clear();
        }
    }

    public static void main(String[] args) {
        MessageLog appendOnly = new AppendOnlyLog();
        appendOnly.append("one");
        appendOnly.append("two");
        System.out.println("append-only size before clear=" + appendOnly.size());
        try {
            appendOnly.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("append-only clear unsupported");
        }

        MessageLog editable = new EditableLog();
        editable.append("one");
        editable.clear();
        System.out.println("editable size after clear=" + editable.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac JavadocContractDemo.java
java JavadocContractDemo
```

Stdout chính xác:

```text
append-only size before clear=2
append-only clear unsupported
editable size after clear=0
```

`AppendOnlyLog` không override `clear()`, nên lời gọi dùng phần thân default và ném `UnsupportedOperationException`. `EditableLog` override cùng phương thức nên thao tác xóa thành công. Cả hai vẫn là `MessageLog`, nhưng khả năng hỗ trợ thao tác khác nhau theo hợp đồng được mô tả. Trong API thật, caller nên đọc tài liệu và không giả định thao tác tùy chọn luôn thành công.

Ví dụ này minh họa cơ chế ngôn ngữ. Với API công khai, cần cân nhắc kỹ việc thêm thao tác tùy chọn vào interface và ghi rõ điều kiện hỗ trợ, side effect, tính an toàn khi gọi lặp lại và exception.

## 7. Thêm default method vào interface đã tồn tại: lợi ích và rủi ro

Default method cho phép tác giả thư viện bổ sung một hành vi chung mà nhiều class cũ có thể kế thừa, thay vì buộc mọi implementation viết lại ngay một method mới. Đây là lý do default method quan trọng với các interface của JDK và thư viện có nhiều implementation.

Tuy nhiên, thêm default method không phải lúc nào cũng hoàn toàn không có rủi ro:

- Một class đã có method cùng chữ ký có thể chọn method của class theo quy tắc ưu tiên, dẫn đến hành vi khác với dự đoán của tác giả interface.
- Khi một class triển khai nhiều interface, default method cùng chữ ký có thể tạo xung đột cần override.
- Hành vi mặc định mới có thể không phù hợp với invariant hoặc giới hạn của một implementation cũ, ngay cả khi mã vẫn biên dịch.
- Javadoc phải mô tả hợp đồng rõ ràng, bao gồm điều kiện hỗ trợ, exception và ảnh hưởng đến trạng thái.

Khi nâng cấp JDK hoặc thư viện, hãy xem tài liệu của phiên bản đang dùng và kiểm tra các implementation liên quan; đừng giả định default method luôn tự động phù hợp với mọi lớp hiện có.

## 8. Checklist khi đọc một API trong JDK

Trước khi dùng hoặc triển khai phương thức, hãy tự trả lời:

- Phương thức abstract, default hay static? Nếu default, phần thân mặc định làm gì?
- Javadoc có ghi “optional operation” không? Nếu có, exception nào được quy định khi không hỗ trợ?
- `@implSpec` có đặt ra điều kiện hoặc yêu cầu mà implementation phải tuân thủ không?
- `@implNote` chỉ mô tả chi tiết nội bộ nào? Chi tiết đó có thực sự là cam kết công khai không?
- Các `@param`, `@return` và `@throws` nói gì về `null`, mutability, trạng thái, kết quả và lỗi?
- Nếu override, implementation có giữ nguyên hợp đồng mà caller dựa vào không?
- Nếu nhiều interface cung cấp default method cùng chữ ký, quy tắc kế thừa nào áp dụng?
- Nếu nâng cấp thư viện, default method mới có tương thích về hành vi với implementation hiện tại không?

## Kết luận

Khi đọc Javadoc, hãy tách hợp đồng API khỏi chi tiết triển khai. `@implSpec` giúp hiểu yêu cầu dành cho implementation; `@implNote` cung cấp ghi chú kỹ thuật; “optional operation” cho biết một thao tác có thể không được hỗ trợ; `default` cho biết interface có sẵn phần thân instance để kế thừa. Đọc đồng thời chữ ký, mô tả, `@throws` và các ghi chú này sẽ giúp triển khai interface đúng hợp đồng và tránh giả định sai về hành vi của API trong JDK.